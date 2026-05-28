"""Local control panel for the classifier toolkit.

A 127.0.0.1-bound web app (sibling to review_server.py) that lists every
operator script — prioritised by how often you'd reach for it now that the
bulk migration is done — and runs them on one click, showing live status.

NOT a cloud app: every script needs the local vault, LM Studio, and venv,
so this must run on the operator's machine. Binding to 127.0.0.1 also keeps
the vault-deleting scripts off the public internet.

Security boundary: POST /run accepts a registry KEY (see script_registry),
never a command string — there is no path to arbitrary command execution.

Usage:
    scripts/classify/venv/bin/python scripts/classify/control_panel.py --port 8770
"""

from __future__ import annotations

import argparse
import html as _html
import json
import subprocess
import sys
import threading
import tomllib
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote

# Allow direct script invocation (`python scripts/classify/control_panel.py`).
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.classify import script_registry as reg


def _read_version() -> str:
    """Single source of truth for the version: pyproject.toml."""
    try:
        with open(_REPO_ROOT / "pyproject.toml", "rb") as f:
            return tomllib.load(f)["project"]["version"]
    except (OSError, KeyError, tomllib.TOMLDecodeError):
        return "0.0.0"


__version__ = _read_version()

_DEFAULT_PORT = 8770
_DEFAULT_VAULT = Path.home() / "Documents" / "ObsidianVault" / "Personal"


class JobManager:
    """Runs registry scripts as async subprocesses, one at a time.

    ``start_job`` spawns the process and returns a job_id immediately; a
    daemon thread drains combined stdout/stderr into a buffer and flips the
    job state to ``complete``/``failed`` when the process exits. One job at
    a time (v1) — ``start_job`` raises while a job is active so two
    long-running scripts can't corrupt the vault concurrently.

    In-memory state only (single local user, single process). Jobs are lost
    on restart, which is acceptable — there's no history requirement.
    """

    def __init__(self) -> None:
        self._jobs: dict[str, dict[str, Any]] = {}
        self._active_id: str | None = None
        # Long-running servers, tracked by registry key, separate from the
        # one-shot job slot so a running server never blocks a classify run.
        self._servers: dict[str, dict[str, Any]] = {}
        self._server_procs: dict[str, subprocess.Popen] = {}
        self._lock = threading.Lock()

    def is_busy(self) -> bool:
        with self._lock:
            return self._active_id is not None

    def start_job(self, key: str, entry: dict[str, Any]) -> str:
        """Spawn ``[entry['interpreter'], *entry['argv']]`` in ``entry['cwd']``.
        Returns a job_id. Raises RuntimeError if a job is already running."""
        with self._lock:
            if self._active_id is not None:
                raise RuntimeError(
                    "a job is already running — one at a time"
                )
            job_id = uuid.uuid4().hex
            self._jobs[job_id] = {
                "state": "running",
                "exit_code": None,
                "output": "",
                "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "key": key,
            }
            self._active_id = job_id

        cmd = [entry["interpreter"], *entry["argv"]]
        try:
            proc = subprocess.Popen(
                cmd,
                cwd=entry["cwd"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
        except OSError as e:
            # Spawn itself failed (bad interpreter path, etc.) — mark failed
            # and release the slot rather than wedging the manager.
            with self._lock:
                self._jobs[job_id]["state"] = "failed"
                self._jobs[job_id]["exit_code"] = -1
                self._jobs[job_id]["output"] = f"failed to start: {e}"
                self._active_id = None
            return job_id

        thread = threading.Thread(
            target=self._drain, args=(job_id, proc), daemon=True,
        )
        thread.start()
        return job_id

    def _drain(self, job_id: str, proc: subprocess.Popen) -> None:
        """Stream the subprocess output into the job buffer, then record the
        exit code + final state. Runs in a daemon thread."""
        assert proc.stdout is not None
        for line in proc.stdout:
            with self._lock:
                self._jobs[job_id]["output"] += line
        proc.wait()
        with self._lock:
            self._jobs[job_id]["exit_code"] = proc.returncode
            self._jobs[job_id]["state"] = (
                "complete" if proc.returncode == 0 else "failed"
            )
            self._active_id = None

    def get_status(self, job_id: str) -> dict[str, Any]:
        """Return a snapshot of the job's state. Raises KeyError if unknown."""
        with self._lock:
            if job_id not in self._jobs:
                raise KeyError(job_id)
            return dict(self._jobs[job_id])

    # ---- Long-running servers (start/stop), independent of the job slot ----

    def start_server(self, key: str, entry: dict[str, Any]) -> dict[str, Any]:
        """Spawn a long-running server process tracked by ``key``. Does NOT
        occupy the one-shot job slot, so a running server never blocks a
        classify run. Raises RuntimeError if one is already running for key."""
        with self._lock:
            existing = self._servers.get(key)
            if existing and existing["state"] == "running":
                raise RuntimeError(f"server {key} is already running")
            rec = {
                "state": "running",
                "pid": None,
                "url": entry.get("url"),
                "output": "",
                "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "key": key,
            }
            self._servers[key] = rec

        cmd = [entry["interpreter"], *entry["argv"]]
        try:
            proc = subprocess.Popen(
                cmd, cwd=entry["cwd"],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1,
            )
        except OSError as e:
            with self._lock:
                rec["state"] = "failed"
                rec["output"] = f"failed to start: {e}"
            return self.server_status(key)

        with self._lock:
            rec["pid"] = proc.pid
            self._server_procs[key] = proc
        threading.Thread(
            target=self._drain_server, args=(key, proc), daemon=True,
        ).start()
        return self.server_status(key)

    def _drain_server(self, key: str, proc: subprocess.Popen) -> None:
        """Stream a server's output into its record; mark stopped on exit."""
        assert proc.stdout is not None
        for line in proc.stdout:
            with self._lock:
                if key in self._servers:
                    self._servers[key]["output"] += line
        proc.wait()
        with self._lock:
            if key in self._servers:
                self._servers[key]["state"] = "stopped"
            self._server_procs.pop(key, None)

    def stop_server(self, key: str) -> dict[str, Any]:
        """Terminate the server for ``key`` (escalating to kill after a short
        grace). Raises RuntimeError if no server is running for that key."""
        with self._lock:
            proc = self._server_procs.get(key)
            rec = self._servers.get(key)
            if proc is None or rec is None or rec["state"] != "running":
                raise RuntimeError(f"server {key} is not running")
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)
        with self._lock:
            if key in self._servers:
                self._servers[key]["state"] = "stopped"
            self._server_procs.pop(key, None)
        return self.server_status(key)

    def server_status(self, key: str) -> dict[str, Any]:
        """Snapshot of a server's state. Raises KeyError if never started."""
        with self._lock:
            if key not in self._servers:
                raise KeyError(key)
            return dict(self._servers[key])

_TIER_HEADINGS = {
    "daily": "Daily",
    "occasional": "Occasional",
    "done": "Done",
    "link": "Servers",
}
_TIER_SUBLABELS = {
    "daily": "Your ongoing loop",
    "occasional": "Upcoming",
    "done": "One-time migrations &mdash; complete",
    "link": "Launch separately",
}

# Geist + Geist Mono — the SprintTracker reference design's typefaces.
# Loaded from Google Fonts; system-font fallbacks keep it readable offline.
_FONT_LINKS = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
    '<link href="https://fonts.googleapis.com/css2?family=Geist:wght@400;500;600;700&family=Geist+Mono:wght@400;500&display=swap" rel="stylesheet">'
)

_PAGE_CSS = """
/* Palette + type matched to the SprintTracker reference design:
   gray-950 surfaces, gray-900 cards, gray-800 borders, green-500 accent,
   Geist + Geist Mono. */
:root {
  --bg: #030712;          /* gray-950 */
  --card: #111827;        /* gray-900 */
  --elevated: #0b1220;
  --border: #1f2937;      /* gray-800 */
  --border-soft: #161e2b;
  --text: #ededed;
  --text-2: #d1d5db;      /* gray-300 */
  --dim: #9ca3af;         /* gray-400 */
  --faint: #6b7280;       /* gray-500 */
  --fainter: #4b5563;     /* gray-600 */
  --accent: #22c55e;      /* green-500 */
  --accent-text: #4ade80; /* green-400 */
  --accent-deep: #030712;
  --warn: #f59e0b;        /* amber-500 */
  --err: #ef4444;         /* red-500 */
  --radius: 0.75rem;
  --sans: "Geist", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  --mono: "Geist Mono", ui-monospace, SFMono-Regular, Menlo, monospace;
}
* { box-sizing: border-box; }
html, body { margin: 0; padding: 0; height: 100%; }
body {
  background: var(--bg); color: var(--text-2); font-family: var(--sans);
  font-size: 14px; line-height: 1.5; -webkit-font-smoothing: antialiased; overflow: hidden;
}

/* ---- App shell: sidebar + main ---- */
.shell { display: grid; grid-template-columns: 296px 1fr; height: 100vh; }

/* ---- Sidebar (aside) ---- */
.rail { overflow-y: auto; border-right: 1px solid var(--border); background: var(--bg);
  display: flex; flex-direction: column; }
.brand { display: flex; align-items: center; gap: 12px; padding: 22px 22px 18px; }
.brand .mark { width: 40px; height: 40px; border-radius: var(--radius); flex-shrink: 0;
  background: rgba(20,83,45,0.30); border: 1px solid #166534;
  display: flex; align-items: center; justify-content: center; color: var(--accent-text); }
.brand .mark svg { width: 20px; height: 20px; }
.brand h1 { font-size: 15px; font-weight: 700; color: #fff; margin: 0; letter-spacing: -0.01em; }
.brand .tag { font-family: var(--mono); font-size: 10px; letter-spacing: 0.14em;
  text-transform: uppercase; color: var(--faint); margin-top: 2px; }

nav.tiers { flex: 1; padding: 8px 12px 32px; }
.tier { margin-bottom: 20px; }
.tier-head { padding: 0 12px; margin-bottom: 6px; }
.tier-title { font-family: var(--mono); font-size: 10px; text-transform: uppercase;
  letter-spacing: 0.16em; color: var(--fainter); font-weight: 600; }
.tier-sub { font-size: 11px; color: var(--faint); margin-top: 1px; }

article.tool { display: flex; align-items: center; gap: 11px; width: 100%; text-align: left;
  padding: 9px 12px; border-radius: var(--radius); border: 1px solid transparent; cursor: pointer;
  background: none; color: inherit; font: inherit; margin-bottom: 2px;
  transition: background 0.12s, border-color 0.12s, color 0.12s; }
article.tool:hover { background: var(--card); color: var(--text); }
article.tool.active { background: rgba(34,197,94,0.10); border-color: rgba(34,197,94,0.30); }
article.tool:focus-visible { outline: 2px solid var(--accent); outline-offset: 1px; }
article.tool.tier-done { opacity: 0.55; }
article.tool.tier-done.active, article.tool.tier-done:hover { opacity: 1; }
.tool .dot { width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; background: var(--fainter); }
.tool .dot.running { background: var(--warn); box-shadow: 0 0 7px var(--warn);
  animation: pulse 1.3s ease-in-out infinite; }
.tool .dot.complete { background: var(--accent); box-shadow: 0 0 7px var(--accent); }
.tool .dot.failed { background: var(--err); box-shadow: 0 0 7px var(--err); }
.tool .tool-text { min-width: 0; }
.tool .tool-name { font-weight: 600; font-size: 13.5px; color: var(--text-2); }
.tool:hover .tool-name { color: var(--text); }
.tool.active .tool-name { color: var(--accent-text); font-weight: 600; }
.tool .tool-desc { font-size: 12px; color: var(--dim); margin-top: 3px; line-height: 1.45;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }

/* ---- Main: detail + console ---- */
.workspace { display: flex; flex-direction: column; min-height: 0; background: var(--bg); }
.detail { padding: 28px 34px 22px; border-bottom: 1px solid var(--border); }
.detail-badge { display: inline-flex; align-items: center; gap: 7px; font-family: var(--mono);
  font-size: 10px; letter-spacing: 0.12em; text-transform: uppercase; color: var(--accent-text);
  background: rgba(34,197,94,0.08); border: 1px solid rgba(34,197,94,0.25);
  border-radius: 999px; padding: 4px 12px; margin-bottom: 14px; }
.detail h2 { font-size: 26px; font-weight: 700; color: #fff; letter-spacing: -0.02em; margin: 0 0 8px; }
.detail .use { color: var(--text-2); font-size: 15px; line-height: 1.6; max-width: 64ch; margin: 0 0 20px; }
.cmd-label { font-family: var(--mono); font-size: 10px; letter-spacing: 0.12em;
  text-transform: uppercase; color: var(--faint); margin-bottom: 6px; }
.cmd { font-family: var(--mono); font-size: 12.5px; color: var(--accent-text);
  background: var(--card); border: 1px solid var(--border); border-radius: var(--radius);
  padding: 12px 14px; overflow-x: auto; white-space: pre; margin-bottom: 20px; }
.run-row { display: flex; align-items: center; gap: 16px; }
button.run { font-family: var(--sans); font-weight: 600; font-size: 14px; color: var(--accent-deep);
  cursor: pointer; border: none; border-radius: var(--radius); padding: 10px 24px;
  background: var(--accent); transition: background 0.15s, transform 0.1s; }
button.run:hover:not(:disabled) { background: var(--accent-text); }
button.run:active:not(:disabled) { transform: scale(0.97); }
button.run:disabled { opacity: 0.4; cursor: not-allowed; }
button.run.secondary { background: transparent; color: var(--text-2);
  border: 1px solid var(--border); }
button.run.secondary:hover:not(:disabled) { background: var(--card); color: var(--text); border-color: var(--err); }
.open-link { font-family: var(--sans); font-weight: 600; font-size: 14px; text-decoration: none;
  color: var(--accent-text); border: 1px solid rgba(34,197,94,0.4); border-radius: var(--radius);
  padding: 9px 18px; transition: background 0.12s; }
.open-link:hover { background: rgba(34,197,94,0.10); }
.run-hint { font-size: 12.5px; color: var(--dim); }

/* ---- Console (gray-900 card, like a SprintTracker panel) ---- */
.console { flex: 1; min-height: 0; display: flex; flex-direction: column; margin: 20px 34px 26px;
  border: 1px solid var(--border); border-radius: var(--radius); overflow: hidden; background: var(--card); }
.console-head { display: flex; align-items: center; justify-content: space-between;
  padding: 11px 16px; border-bottom: 1px solid var(--border); background: var(--elevated); }
.console-head .label { font-family: var(--mono); font-size: 11px; letter-spacing: 0.12em;
  text-transform: uppercase; color: var(--dim); }
.pill { font-family: var(--mono); font-size: 11px; padding: 4px 12px; border-radius: 999px;
  display: inline-flex; align-items: center; gap: 7px; text-transform: uppercase; letter-spacing: 0.06em;
  background: rgba(255,255,255,0.04); color: var(--faint); border: 1px solid var(--border); }
.pill::before { content: ""; width: 6px; height: 6px; border-radius: 50%; background: currentColor; }
.pill.running { color: var(--warn); border-color: rgba(245,158,11,0.4); }
.pill.running::before { animation: pulse 1.3s ease-in-out infinite; }
.pill.complete { color: var(--accent-text); border-color: rgba(34,197,94,0.4); }
.pill.failed { color: var(--err); border-color: rgba(239,68,68,0.4); }
.console-body { flex: 1; overflow: auto; padding: 16px; margin: 0; background: var(--bg);
  font-family: var(--mono); font-size: 12px; line-height: 1.6; color: var(--text-2);
  white-space: pre-wrap; }
.console-body.empty { display: flex; align-items: center; justify-content: center;
  color: var(--faint); font-family: var(--sans); }
.console-body a { color: var(--accent-text); text-decoration: underline;
  text-underline-offset: 2px; }
.console-body a:hover { color: #86efac; }

@keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.4; } }
@media (prefers-reduced-motion: reduce) { .dot, .pill::before { animation: none !important; } }
::-webkit-scrollbar { width: 10px; height: 10px; }
::-webkit-scrollbar-thumb { background: var(--border); border-radius: 6px; }
::-webkit-scrollbar-thumb:hover { background: #2d3748; }
"""

_PAGE_JS = """
const detail = {
  badge: null, name: null, use: null, cmd: null, run: null, hint: null,
  start: null, stop: null, open: null,
};
let consoleHead, consoleBody, consolePill, consoleLabel, currentKey = null, currentKind = '';

function init() {
  detail.badge = document.getElementById('d-badge');
  detail.name = document.getElementById('d-name');
  detail.use = document.getElementById('d-use');
  detail.cmd = document.getElementById('d-cmd');
  detail.run = document.getElementById('d-run');
  detail.hint = document.getElementById('d-hint');
  detail.start = document.getElementById('d-start');
  detail.stop = document.getElementById('d-stop');
  detail.open = document.getElementById('d-open');
  consolePill = document.getElementById('c-pill');
  consoleLabel = document.getElementById('c-label');
  consoleBody = document.getElementById('c-body');
  document.querySelectorAll('article.tool').forEach(row => {
    row.addEventListener('click', () => selectTool(row));
  });
  detail.run.addEventListener('click', runCurrent);
  detail.start.addEventListener('click', startServer);
  detail.stop.addEventListener('click', stopServer);
  const first = document.querySelector('article.tool:not(.tier-link)');
  if (first) selectTool(first);
}

const TIER_LABEL = {daily: 'Daily tool', occasional: 'Occasional', done: 'Done — one-time', link: 'Server'};

function selectTool(row) {
  document.querySelectorAll('article.tool').forEach(t => t.classList.remove('active'));
  row.classList.add('active');
  const d = row.dataset;
  currentKey = d.key;
  currentKind = d.kind || '';
  detail.badge.textContent = TIER_LABEL[d.tier] || d.tier;
  detail.name.textContent = d.name;
  detail.use.textContent = d.use;
  detail.cmd.textContent = d.cmd || '—';
  const isServer = d.kind === 'server';
  const isLink = d.tier === 'link' && !isServer;
  detail.run.style.display = (isServer || isLink) ? 'none' : '';
  detail.start.style.display = isServer ? '' : 'none';
  detail.stop.style.display = isServer ? '' : 'none';
  detail.open.style.display = isServer ? '' : 'none';
  if (isServer) {
    detail.open.href = d.url || '#';
    detail.hint.textContent = 'Starts a background server. Stop it here when you are done.';
    refreshServer(d.key);
  } else {
    detail.hint.textContent = isLink
      ? 'Launch this server separately from a terminal, then open its own page.'
      : (d.dry === '1' ? 'Safe preview — no changes are written.'
         : 'This makes real changes to the vault.');
  }
}

async function refreshServer(key) {
  try {
    const res = await fetch('/server/status/' + encodeURIComponent(key));
    const data = await res.json();
    applyServerState(data);
  } catch (e) { /* leave controls as-is */ }
}

function applyServerState(data) {
  const running = data.state === 'running';
  detail.start.disabled = running;
  detail.stop.disabled = !running;
  if (data.url) detail.open.href = data.url;
  setStatus(running ? 'running' : (data.state === 'failed' ? 'failed' : ''),
            running ? 'running' : (data.state || 'stopped'));
  if (data.output) {
    consoleBody.classList.remove('empty');
    consoleBody.textContent = data.output;
  }
}

async function startServer() {
  if (!currentKey) return;
  detail.start.disabled = true;
  consoleLabel.firstChild.textContent = detail.name.textContent + ' ';
  setStatus('running', 'starting');
  try {
    const res = await fetch('/server/start', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({key: currentKey})
    });
    const data = await res.json();
    if (!res.ok) { setStatus('failed', res.status === 409 ? 'already running' : 'rejected');
      consoleBody.classList.remove('empty'); consoleBody.textContent = data.error || ('HTTP ' + res.status);
      detail.start.disabled = false; return; }
    applyServerState(data);
  } catch (e) { setStatus('failed', 'error'); detail.start.disabled = false; }
}

async function stopServer() {
  if (!currentKey) return;
  detail.stop.disabled = true;
  try {
    const res = await fetch('/server/stop', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({key: currentKey})
    });
    const data = await res.json();
    if (!res.ok) { setStatus('failed', 'error');
      consoleBody.classList.remove('empty'); consoleBody.textContent = data.error || ('HTTP ' + res.status);
      detail.stop.disabled = false; return; }
    applyServerState(data);
  } catch (e) { detail.stop.disabled = false; }
}

function setStatus(state, text) {
  consolePill.className = 'pill ' + (state || '');
  consolePill.textContent = text || (state || 'idle');
}

async function runCurrent() {
  if (!currentKey) return;
  detail.run.disabled = true;
  consoleLabel.firstChild.textContent = detail.name.textContent + ' ';
  consoleBody.classList.remove('empty');
  consoleBody.textContent = '';
  setStatus('running', 'running');
  try {
    const res = await fetch('/run', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({key: currentKey})
    });
    if (!res.ok) {
      let msg = ''; try { msg = (await res.json()).error || ''; } catch (e) { msg = await res.text(); }
      setStatus('failed', res.status === 409 ? 'busy' : 'rejected');
      consoleBody.textContent = msg || ('HTTP ' + res.status);
      detail.run.disabled = false;
      return;
    }
    const {job_id} = await res.json();
    poll(job_id);
  } catch (e) {
    setStatus('failed', 'error');
    consoleBody.textContent = String(e);
    detail.run.disabled = false;
  }
}

async function poll(jobId) {
  const res = await fetch('/status/' + jobId);
  const data = await res.json();
  if (data.output_html != null) { consoleBody.innerHTML = data.output_html; consoleBody.scrollTop = consoleBody.scrollHeight; }
  else if (data.output) { consoleBody.textContent = data.output; consoleBody.scrollTop = consoleBody.scrollHeight; }
  if (data.state === 'running') {
    setStatus('running', 'running');
    setTimeout(() => poll(jobId), 1200);
  } else {
    setStatus(data.state, data.state + (data.exit_code != null ? ' · exit ' + data.exit_code : ''));
    detail.run.disabled = false;
  }
}

document.addEventListener('DOMContentLoaded', init);
"""


_NOTE_DECISIONS = ("auto", "review", "purged")


def linkify_console_output(text: str, vault_name: str) -> str:
    """HTML-escape console output and turn classify ``--log-notes`` lines
    (``<decision>\\t<relpath>.md[\\t...]``) into clickable ``obsidian://``
    links. Everything is escaped first, so the only live markup is the
    anchors we build — no path for the subprocess output to inject HTML."""
    return "\n".join(_linkify_line(line, vault_name) for line in text.split("\n"))


def _linkify_line(line: str, vault_name: str) -> str:
    parts = line.split("\t")
    if len(parts) >= 2 and parts[0] in _NOTE_DECISIONS and parts[1].endswith(".md"):
        path = parts[1]
        href = f"obsidian://open?vault={quote(vault_name)}&file={quote(path)}"
        anchor = f'<a href="{_html.escape(href, quote=True)}">{_html.escape(path)}</a>'
        head = _html.escape(parts[0]) + "\t"
        rest = parts[2:]
        tail = ("\t" + _html.escape("\t".join(rest))) if rest else ""
        return head + anchor + tail
    return _html.escape(line)


def _command_preview(entry: dict[str, Any]) -> str:
    """Human-readable command the Run button will execute. Shows the
    interpreter basename + argv so the operator sees exactly what runs.
    Link-tier entries have no command."""
    if entry["tier"] == "link":
        return ""
    interp = Path(entry["interpreter"]).name
    return " ".join([interp, *entry["argv"]])


def _is_dry(entry: dict[str, Any]) -> bool:
    """True if this is a safe preview variant (no writes)."""
    return "--dry-run" in entry.get("argv", []) or entry["key"].endswith("-dry")


def _render_tool_row(entry: dict[str, Any], job_state: dict | None) -> str:
    """One selectable sidebar row. Carries the tool's metadata as data-*
    attributes so the JS can populate the detail pane without a round-trip,
    and a status dot reflecting any active job for this key."""
    name = _html.escape(entry["name"])
    use = _html.escape(entry["use_case"])
    key = _html.escape(entry["key"])
    tier = entry["tier"]
    cmd = _html.escape(_command_preview(entry))
    desc = _html.escape(entry["use_case"])
    classes = "tool"
    if tier == "done":
        classes += " tier-done"
    if tier == "link":
        classes += " tier-link"
    state = (job_state or {}).get("state", "")
    dot_cls = f"dot {state}" if state else "dot"
    dry = "1" if _is_dry(entry) else "0"
    kind = _html.escape(entry.get("kind", ""))
    url = _html.escape(entry.get("url", ""))

    return (
        f'<article class="{classes}" tabindex="0" '
        f'data-key="{key}" data-name="{name}" data-use="{use}" '
        f'data-cmd="{cmd}" data-tier="{tier}" data-dry="{dry}" '
        f'data-kind="{kind}" data-url="{url}">'
        f'<span class="{dot_cls}"></span>'
        f'<span class="tool-text">'
        f'<span class="tool-name">{name}</span>'
        f'<span class="tool-desc">{desc}</span>'
        f'</span>'
        f'</article>'
    )


def render_catalog(job_states: dict[str, dict] | None = None) -> str:
    """Render the control-panel app shell: a top bar, a tier-grouped tool
    rail, and a workspace (detail panel + console). ``job_states`` maps a
    registry key to its current job status so a row's status dot reflects an
    active run on first paint; live updates after that are driven by the JS
    polling /status."""
    job_states = job_states or {}

    rail_sections = []
    for tier, entries in reg.by_tier().items():
        title = _TIER_HEADINGS.get(tier, tier)
        sub = _TIER_SUBLABELS.get(tier, "")
        rows = "".join(
            _render_tool_row(e, job_states.get(e["key"])) for e in entries
        )
        rail_sections.append(
            f'<div class="tier"><div class="tier-head">'
            f'<div class="tier-title">{title}</div>'
            f'<div class="tier-sub">{sub}</div></div>{rows}</div>'
        )
    rail = "".join(rail_sections)

    return (
        "<!doctype html>\n<html lang=\"en\">\n<head>\n"
        "<meta charset=\"utf-8\">\n"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
        "<title>Obsidian Vault Control Panel</title>\n"
        f"{_FONT_LINKS}\n"
        f"<style>{_PAGE_CSS}</style>\n</head>\n<body>\n"
        '<div class="shell">\n'
        '<aside class="rail">\n'
        '<div class="brand">'
        '<span class="mark"><svg viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" stroke-width="2" stroke-linecap="round" '
        'stroke-linejoin="round"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>'
        "</svg></span>"
        '<div><h1>Obsidian Vault Control</h1>'
        f'<div class="tag">Operator Console · v{__version__}</div></div>'
        "</div>\n"
        f'<nav class="tiers">{rail}</nav>\n'
        "</aside>\n"
        '<main class="workspace">\n'
        '<section class="detail">'
        '<span class="detail-badge" id="d-badge">Daily tool</span>'
        '<h2 id="d-name">Select a tool</h2>'
        '<p class="use" id="d-use">Pick a script from the left to see what it '
        'does and when to run it.</p>'
        '<div class="cmd-label">Command</div>'
        '<div class="cmd" id="d-cmd">—</div>'
        '<div class="run-row">'
        '<button class="run" id="d-run">Run</button>'
        '<button class="run" id="d-start" style="display:none">Start server</button>'
        '<button class="run secondary" id="d-stop" style="display:none">Stop</button>'
        '<a class="open-link" id="d-open" style="display:none" target="_blank" rel="noopener">Open &#8599;</a>'
        '<span class="run-hint" id="d-hint"></span>'
        "</div>"
        "</section>\n"
        '<section class="console">'
        '<div class="console-head">'
        '<span class="label" id="c-label"><span>Console</span></span>'
        '<span class="pill" id="c-pill">idle</span>'
        "</div>"
        '<pre class="console-body empty" id="c-body">No output yet — select a '
        "tool and press Run.</pre>"
        "</section>\n"
        "</main>\n"
        "</div>\n"
        f"<script>{_PAGE_JS}</script>\n"
        "</body>\n</html>\n"
    )


# ---------------------------------------------------------------------------
# HTTP server — 127.0.0.1 only, sibling to review_server.py.


class _Handler(BaseHTTPRequestHandler):
    # Server-injected (set on the HTTPServer instance by start_server).
    @property
    def _jobs(self) -> JobManager:
        return self.server._job_manager  # type: ignore[attr-defined]

    @property
    def _resolve(self) -> Callable[[str], dict]:
        return self.server._resolve  # type: ignore[attr-defined]

    def log_message(self, *args: Any) -> None:  # noqa: A003 - silence default logging
        pass

    def _send_json(self, code: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, code: int, html: str) -> None:
        body = html.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health":
            self._send_json(200, {"ok": True, "version": __version__, "vault": str(self.server._vault)})  # type: ignore[attr-defined]
            return
        if self.path == "/" or self.path.startswith("/?"):
            self._send_html(200, render_catalog())
            return
        if self.path.startswith("/status/"):
            job_id = self.path[len("/status/"):]
            try:
                status = self._jobs.get_status(job_id)
            except KeyError:
                self._send_json(404, {"error": "unknown job"})
                return
            status["output_html"] = linkify_console_output(
                status.get("output", ""), self.server._vault.name,  # type: ignore[attr-defined]
            )
            self._send_json(200, status)
            return
        if self.path.startswith("/server/status/"):
            key = self.path[len("/server/status/"):]
            try:
                self._send_json(200, self._jobs.server_status(key))
            except KeyError:
                # Never started — report stopped, with the url if it's a known
                # server so the UI's Open link still works.
                url = None
                try:
                    url = self._resolve(key).get("url")
                except KeyError:
                    pass
                self._send_json(200, {"state": "stopped", "key": key, "url": url})
            return
        self._send_json(404, {"error": "not found"})

    def _read_key(self) -> str | None:
        """Read {'key': ...} from the request body. Sends 400 and returns
        None if missing/invalid."""
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            return json.loads(raw)["key"]
        except (json.JSONDecodeError, KeyError, TypeError):
            self._send_json(400, {"error": "missing or invalid 'key'"})
            return None

    def do_POST(self) -> None:  # noqa: N802
        if self.path == "/run":
            self._handle_run()
            return
        if self.path == "/server/start":
            self._handle_server_start()
            return
        if self.path == "/server/stop":
            self._handle_server_stop()
            return
        self._send_json(404, {"error": "not found"})

    def _handle_run(self) -> None:
        key = self._read_key()
        if key is None:
            return
        try:
            entry = self._resolve(key)
        except KeyError:
            self._send_json(400, {"error": f"unknown script key: {key}"})
            return
        try:
            job_id = self._jobs.start_job(key, entry)
        except RuntimeError as e:
            self._send_json(409, {"error": str(e)})
            return
        self._send_json(200, {"job_id": job_id})

    def _handle_server_start(self) -> None:
        key = self._read_key()
        if key is None:
            return
        try:
            entry = self._resolve(key)
        except KeyError:
            self._send_json(400, {"error": f"unknown server key: {key}"})
            return
        if entry.get("kind") != "server":
            self._send_json(400, {"error": f"{key} is not a server"})
            return
        try:
            status = self._jobs.start_server(key, entry)
        except RuntimeError as e:
            self._send_json(409, {"error": str(e)})
            return
        self._send_json(200, status)

    def _handle_server_stop(self) -> None:
        key = self._read_key()
        if key is None:
            return
        try:
            status = self._jobs.stop_server(key)
        except RuntimeError as e:
            self._send_json(409, {"error": str(e)})
            return
        self._send_json(200, status)


def start_server(
    host: str = "127.0.0.1",
    port: int = _DEFAULT_PORT,
    vault: Path = _DEFAULT_VAULT,
    resolve: Callable[[str], dict] | None = None,
    job_manager: JobManager | None = None,
) -> HTTPServer:
    """Build (but do not serve) the control-panel HTTP server bound to
    127.0.0.1. ``resolve`` maps a registry key to its entry (defaults to the
    real registry); injectable so tests run trivial commands instead of real
    vault scripts."""
    server = HTTPServer((host, port), _Handler)
    server._job_manager = job_manager or JobManager()  # type: ignore[attr-defined]
    server._resolve = resolve or reg.get  # type: ignore[attr-defined]
    server._vault = vault  # type: ignore[attr-defined]
    return server


_CLI_DESCRIPTION = """\
Local control panel for the classifier toolkit. Serves a dashboard at
http://127.0.0.1:<port> listing every operator script (prioritised), with a
one-click Run button and live status. Bound to 127.0.0.1 only — the
vault-mutating scripts never face the public internet.
"""


def main() -> None:
    parser = argparse.ArgumentParser(
        description=_CLI_DESCRIPTION,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--port", type=int, default=_DEFAULT_PORT,
        help=f"Port to bind on 127.0.0.1 (default: {_DEFAULT_PORT}).",
    )
    parser.add_argument(
        "--vault", type=Path, default=_DEFAULT_VAULT,
        help="Vault root (shown on /health; scripts use their own pinned paths).",
    )
    args = parser.parse_args()

    server = start_server(host="127.0.0.1", port=args.port, vault=args.vault)
    url = f"http://127.0.0.1:{args.port}"
    print(f"Control panel: {url}  (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    main()
