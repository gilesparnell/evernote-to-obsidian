"""Self-contained HTML renderers for the classifier audit tools.

Produces a single .html file with embedded CSS and no external assets —
safe to open from the file system, share, or commit alongside the .md
audit outputs.

Each note row carries an obsidian://open URL so the operator can click
straight from the browser into the source note in Obsidian.

Public API:
    render_review_queue_html(queue, vault, generated) -> str
    render_review_queue_html_with_actions(vault) -> str
    parse_review_queue_md(path) -> list[dict]
    render_sample_html(samples, vault) -> str
"""

from __future__ import annotations

import html
import re
import sys
import urllib.parse
from datetime import datetime
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.classify.frontmatter import is_classified, read_frontmatter  # noqa: E402

_BODY_EXCERPT_CHARS = 400

_CSS = """
:root {
  --bg: #0a0c10;
  --surface: rgba(255, 255, 255, 0.04);
  --surface-2: rgba(255, 255, 255, 0.07);
  --border: rgba(255, 255, 255, 0.10);
  --text: #e6e8ec;
  --text-dim: #8a8f99;
  --text-faint: #5a5f69;
  --accent: #38bfa0;
  --high: #38bfa0;
  --medium: #f0b429;
  --low: #e5484d;
}
* { box-sizing: border-box; }
html, body {
  margin: 0;
  padding: 0;
  background: var(--bg);
  color: var(--text);
  font-family: -apple-system, BlinkMacSystemFont, "Inter", "Outfit",
               "Helvetica Neue", sans-serif;
  font-size: 14px;
  line-height: 1.5;
}
body {
  max-width: 1100px;
  margin: 0 auto;
  padding: 32px 24px 96px;
}
header {
  border-bottom: 1px solid var(--border);
  padding-bottom: 20px;
  margin-bottom: 28px;
}
h1 {
  font-size: 22px;
  font-weight: 600;
  margin: 0 0 6px;
  letter-spacing: -0.01em;
}
.meta {
  color: var(--text-dim);
  font-size: 12px;
}
.summary {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 14px 18px;
  margin-bottom: 24px;
  color: var(--text-dim);
  font-size: 13px;
}
.card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 16px 18px;
  margin-bottom: 12px;
  transition: background 0.12s ease;
}
.card:hover {
  background: var(--surface-2);
}
.card-head {
  display: flex;
  align-items: baseline;
  gap: 12px;
  margin-bottom: 8px;
}
.card-head a {
  color: var(--accent);
  text-decoration: none;
  font-weight: 600;
  font-size: 14px;
  word-break: break-word;
}
.card-head a:hover { text-decoration: underline; }
.fields {
  color: var(--text-dim);
  font-size: 12px;
  font-family: ui-monospace, SFMono-Regular, "SF Mono", Menlo, monospace;
  margin: 6px 0;
}
.fields span { margin-right: 14px; }
.fields strong { color: var(--text); font-weight: 500; }
.confidence {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 6px;
  font-family: ui-monospace, SFMono-Regular, monospace;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.02em;
}
.confidence-high { background: rgba(56, 191, 160, 0.15); color: var(--high); }
.confidence-medium { background: rgba(240, 180, 41, 0.15); color: var(--medium); }
.confidence-low { background: rgba(229, 72, 77, 0.18); color: var(--low); }
.reason {
  color: var(--text);
  font-size: 13px;
  margin-top: 6px;
}
.reason::before {
  content: "Reason: ";
  color: var(--text-faint);
}
.excerpt {
  background: rgba(0, 0, 0, 0.25);
  border-left: 2px solid var(--border);
  border-radius: 4px;
  padding: 10px 14px;
  margin-top: 10px;
  color: var(--text-dim);
  font-size: 12px;
  white-space: pre-wrap;
  font-family: ui-monospace, SFMono-Regular, monospace;
  max-height: 200px;
  overflow-y: auto;
}
.empty {
  text-align: center;
  padding: 60px 0;
  color: var(--text-faint);
  font-size: 14px;
}
"""

_HTML_SHELL = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{title}</title>
<style>{css}</style>
</head>
<body>
<header>
  <h1>{title}</h1>
  <div class="meta">{meta}</div>
</header>
{body}
</body>
</html>
"""


def _confidence_class(confidence: float) -> str:
    if confidence >= 0.80:
        return "confidence-high"
    if confidence >= 0.50:
        return "confidence-medium"
    return "confidence-low"


def _obsidian_url(vault_name: str, relative_path: Path) -> str:
    """Build an obsidian://open URL for vault+relative path.

    Obsidian's URL scheme percent-encodes the file param; the .md suffix
    is optional but we keep it for explicitness.
    """
    encoded_path = urllib.parse.quote(str(relative_path), safe="")
    encoded_vault = urllib.parse.quote(vault_name, safe="")
    return f"obsidian://open?vault={encoded_vault}&file={encoded_path}"


def _relative_to_vault(path: Path, vault: Path) -> Path:
    try:
        return path.relative_to(vault)
    except ValueError:
        return path


def _strip_frontmatter_body(text: str) -> str:
    import re
    fm = re.match(r"^---\s*\n.*?\n---\s*\n", text, re.DOTALL)
    return text[fm.end():].strip() if fm else text.strip()


def _body_excerpt(path: Path) -> str:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""
    body = _strip_frontmatter_body(text)
    if len(body) > _BODY_EXCERPT_CHARS:
        return body[:_BODY_EXCERPT_CHARS] + "..."
    return body


def render_review_queue_html(
    queue: list[dict[str, Any]], vault: Path, generated: str
) -> str:
    """Render the review queue (low-confidence classifier outputs) as HTML."""
    vault_name = vault.name
    title = "Classification Review Queue"
    meta = (
        f"Generated: {html.escape(generated)} &middot; "
        f"{len(queue)} notes &middot; vault: {html.escape(vault_name)}"
    )

    if not queue:
        body = (
            '<div class="empty">'
            "0 notes need manual review. ✅"
            "</div>"
        )
        return _HTML_SHELL.format(
            title=html.escape(title), css=_CSS, meta=meta, body=body
        )

    cards: list[str] = []
    cards.append(
        f'<div class="summary">{len(queue)} notes need manual review. '
        "Click a note title to open it in Obsidian.</div>"
    )
    for item in queue:
        path: Path = item["path"]
        rel = _relative_to_vault(path, vault)
        url = _obsidian_url(vault_name, rel)
        conf = float(item["confidence"])
        klass = _confidence_class(conf)
        excerpt = _body_excerpt(path)
        cards.append(
            '<article class="card">'
            f'  <div class="card-head">'
            f'    <a href="{html.escape(url, quote=True)}">'
            f'{html.escape(str(rel))}</a>'
            f'    <span class="confidence {klass}">{conf:.2f}</span>'
            f'  </div>'
            f'  <div class="fields">'
            f'    <span><strong>type:</strong> '
            f'{html.escape(str(item.get("proposed_type", "?")))}</span>'
            f'    <span><strong>org:</strong> '
            f'{html.escape(str(item.get("proposed_org", "?")))}</span>'
            f'  </div>'
            f'  <div class="reason">'
            f'{html.escape(str(item.get("reason", "")))}</div>'
            + (
                f'  <pre class="excerpt">{html.escape(excerpt)}</pre>'
                if excerpt else ""
            )
            + '</article>'
        )

    return _HTML_SHELL.format(
        title=html.escape(title), css=_CSS, meta=meta, body="".join(cards)
    )


# ---------------------------------------------------------------------------
# Review queue rendering with action buttons. Used by the review_server
# helper at GET / — the buttons POST to /delete and /reclassify on the
# same origin so file:// CORS rules don't apply.


_ACTIONS_CSS = """
.actions {
  margin-top: 12px;
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
.actions button {
  background: var(--surface-2);
  color: var(--text);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 6px 12px;
  font-size: 12px;
  font-family: inherit;
  cursor: pointer;
  transition: background 0.12s, border-color 0.12s;
}
.actions button:hover {
  background: rgba(255,255,255,0.10);
  border-color: rgba(255,255,255,0.20);
}
.actions button.danger { color: var(--low); border-color: rgba(229,72,77,0.25); }
.actions button.danger:hover { background: rgba(229,72,77,0.08); border-color: rgba(229,72,77,0.45); }
.actions button.quick { color: var(--accent); border-color: rgba(56,191,160,0.25); }
.actions button.quick:hover { background: rgba(56,191,160,0.08); border-color: rgba(56,191,160,0.45); }
.card.done { opacity: 0.35; }
.card.done .card-head a { text-decoration: line-through; }
.done-badge {
  color: var(--high);
  font-size: 12px;
  font-weight: 600;
  padding: 4px 0;
}
.error-badge { color: var(--low); font-size: 12px; font-weight: 600; padding: 4px 0; }
.banner {
  background: rgba(56,191,160,0.10);
  border: 1px solid rgba(56,191,160,0.25);
  color: var(--text);
  padding: 10px 14px;
  border-radius: 8px;
  font-size: 13px;
  margin-bottom: 16px;
}
.banner code { background: rgba(0,0,0,0.30); padding: 1px 5px; border-radius: 3px; font-size: 12px; }
.select-checkbox {
  width: 16px;
  height: 16px;
  margin: 0 10px 0 0;
  cursor: pointer;
  accent-color: var(--accent);
  flex-shrink: 0;
}
.card.done .select-checkbox { opacity: 0.3; pointer-events: none; }
.selection-toolbar {
  position: fixed;
  bottom: 20px;
  left: 50%;
  transform: translateX(-50%);
  background: rgba(18, 21, 28, 0.96);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 10px 16px;
  display: flex;
  align-items: center;
  gap: 12px;
  box-shadow: 0 12px 40px rgba(0,0,0,0.45);
  backdrop-filter: blur(10px);
  z-index: 10;
}
.selection-toolbar[hidden] { display: none; }
.selection-toolbar .selection-count { color: var(--text); font-size: 13px; font-weight: 500; }
.selection-toolbar .selection-count strong { color: var(--accent); font-weight: 700; }
.selection-toolbar button {
  background: var(--surface-2);
  color: var(--text);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 6px 12px;
  font-size: 12px;
  font-family: inherit;
  cursor: pointer;
}
.selection-toolbar button:hover { background: rgba(255,255,255,0.10); border-color: rgba(255,255,255,0.20); }
.selection-toolbar button.danger { color: var(--low); border-color: rgba(229,72,77,0.30); }
.selection-toolbar button.danger:hover { background: rgba(229,72,77,0.10); border-color: rgba(229,72,77,0.50); }
.select-controls {
  display: flex;
  gap: 8px;
  margin-bottom: 10px;
}
.select-controls button {
  background: transparent;
  color: var(--text-dim);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 4px 10px;
  font-size: 12px;
  font-family: inherit;
  cursor: pointer;
}
.select-controls button:hover { color: var(--text); border-color: rgba(255,255,255,0.18); }
"""

_ACTIONS_JS = r"""
async function doDelete(card, path) {
  if (!confirm('Move to Trash?\n\n' + path)) return;
  try {
    const r = await fetch('/delete', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({path: path}),
    });
    const d = await r.json();
    if (r.ok && d.ok) {
      card.classList.add('done');
      card.querySelector('.actions').innerHTML =
        '<span class="done-badge">Moved to Trash</span>';
    } else {
      card.querySelector('.actions').insertAdjacentHTML(
        'beforeend',
        '<span class="error-badge">Delete failed: ' + (d.error || r.status) + '</span>');
    }
  } catch (e) { alert('Delete failed: ' + e); }
}
async function doReclassify(card, path, presetType, presetOrg) {
  let type_ = presetType;
  let org = presetOrg;
  if (!type_) {
    type_ = prompt(
      'Type — one of:\n' +
      'meeting / technical / reference / recipe / personal / note /\n' +
      'interview / management / application / career / pattern /\n' +
      'journal / project / person / company',
      'reference');
    if (!type_) return;
  }
  if (!org) {
    org = prompt(
      'Org — Amazon / T-Systems / TSC / Parnell Systems / Personal',
      'Amazon');
    if (!org) return;
  }
  try {
    const r = await fetch('/reclassify', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({path: path, type: type_, org: org}),
    });
    const d = await r.json();
    if (r.ok && d.ok) {
      card.classList.add('done');
      card.querySelector('.actions').innerHTML =
        '<span class="done-badge">Reclassified: ' + type_ + ' / ' + org + '</span>';
    } else {
      card.querySelector('.actions').insertAdjacentHTML(
        'beforeend',
        '<span class="error-badge">Reclassify failed: ' + (d.error || r.status) + '</span>');
    }
  } catch (e) { alert('Reclassify failed: ' + e); }
}

// ---- multi-select bulk delete --------------------------------------------

function _selectedPaths() {
  const out = [];
  document.querySelectorAll('.select-checkbox:checked').forEach(cb => {
    if (!cb.closest('.card').classList.contains('done')) {
      out.push(cb.dataset.path);
    }
  });
  return out;
}
function onSelectionChange() {
  const count = _selectedPaths().length;
  const toolbar = document.getElementById('selection-toolbar');
  document.getElementById('selection-count').textContent = count;
  toolbar.hidden = count === 0;
}
function clearSelection() {
  document.querySelectorAll('.select-checkbox:checked').forEach(cb => cb.checked = false);
  onSelectionChange();
}
function selectAllVisible() {
  document.querySelectorAll('.card:not(.done) .select-checkbox').forEach(cb => cb.checked = true);
  onSelectionChange();
}
async function doDeleteSelected() {
  const paths = _selectedPaths();
  if (paths.length === 0) return;
  if (!confirm('Move ' + paths.length + ' note(s) to Trash?\n\nRecoverable from Finder.')) return;
  try {
    const r = await fetch('/delete-bulk', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({paths: paths}),
    });
    const d = await r.json();
    if (r.ok) {
      (d.moved || []).forEach(p => {
        const cb = document.querySelector('.select-checkbox[data-path="' + p.replace(/"/g, '\\"') + '"]');
        if (!cb) return;
        const card = cb.closest('.card');
        card.classList.add('done');
        const actions = card.querySelector('.actions');
        if (actions) actions.innerHTML = '<span class="done-badge">Moved to Trash</span>';
        cb.checked = false;
      });
      if (d.errors && d.errors.length) {
        const summary = d.errors.map(e => '• ' + e.path + ' — ' + e.error).join('\n');
        alert('Some files could not be deleted:\n\n' + summary);
      }
      onSelectionChange();
    } else {
      alert('Bulk delete failed: ' + (d.error || r.status));
    }
  } catch (e) { alert('Bulk delete failed: ' + e); }
}
"""

_HTML_SHELL_WITH_JS = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{title}</title>
<style>{css}</style>
</head>
<body>
<header>
  <h1>{title}</h1>
  <div class="meta">{meta}</div>
</header>
{body}
<script>{js}</script>
</body>
</html>
"""

_REVIEW_ROW_RE = re.compile(
    r"^\|\s+\[\[([^\]]+)\]\]\s+\|\s+(.+?)\s+\|\s+(.+?)\s+\|\s+([\d.]+)\s+\|\s+(.+?)\s+\|\s*$"
)


def parse_review_queue_md(
    path: Path, skip_acted_on: bool = False,
) -> list[dict[str, Any]]:
    """Reconstruct the queue dicts from a saved classification-review.md.

    Inverse of the table emitted by classify_vault._format_review_queue.
    Used by the review server to (re-)render HTML from disc state without
    re-running classification.

    Args:
        path: location of classification-review.md
        skip_acted_on: when True, prune rows whose underlying file has
            been deleted (not on disc) or already classified
            (full R2 frontmatter present). Used by the triage UI so
            already-handled rows disappear on refresh.

    Returns an empty list if the file doesn't exist or all rows
    were pruned.
    """
    if not path.exists():
        return []
    base = path.parent
    queue: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("| [["):  # quick reject for headers + separators
            continue
        match = _REVIEW_ROW_RE.match(line)
        if not match:
            continue
        rel_path, proposed_type, proposed_org, conf, reason = match.groups()
        note_path = base / rel_path
        if skip_acted_on:
            if not note_path.exists():
                continue  # deleted by the operator (e.g. moved to Trash)
            if is_classified(note_path):
                continue  # manually reclassified — full R2 frontmatter set
        queue.append({
            "path": note_path,
            "proposed_type": proposed_type.strip(),
            "proposed_org": proposed_org.strip(),
            "confidence": float(conf),
            "reason": reason.strip(),
        })
    return queue


def render_review_queue_html_with_actions(vault: Path) -> str:
    """Render the review queue with Delete + Reclassify action buttons.

    Buttons POST to /delete and /reclassify on the same origin — meant
    to be served by review_server.py, NOT opened as a static file.
    """
    review_md = vault / "classification-review.md"
    # skip_acted_on=True: hide rows whose file has been deleted or
    # already classified so the page auto-prunes on each refresh.
    queue_all = parse_review_queue_md(review_md, skip_acted_on=False)
    queue = parse_review_queue_md(review_md, skip_acted_on=True)
    acted_on = len(queue_all) - len(queue)
    vault_name = vault.name
    title = "Classification Review · Triage"
    generated = datetime.now().strftime("%Y-%m-%d %H:%M")
    meta_parts = [
        f"{len(queue)} pending",
        f"vault: {html.escape(vault_name)}",
        f"rendered: {generated}",
    ]
    if acted_on > 0:
        meta_parts.insert(1, f"{acted_on} already actioned (hidden)")
    meta = " &middot; ".join(meta_parts)

    css = _CSS + _ACTIONS_CSS
    if not queue:
        body = (
            '<div class="empty">'
            "Review queue is empty. Nothing to triage."
            "</div>"
        )
        return _HTML_SHELL_WITH_JS.format(
            title=html.escape(title), css=css, meta=meta,
            body=body, js="",
        )

    cards: list[str] = []
    cards.append(
        '<div class="banner">'
        "Tick the box on any card to select it. Pick several, then click "
        "<strong>Delete selected</strong> in the floating toolbar to trash "
        "them in one batch. Per-card <strong>Delete</strong> / "
        "<strong>Reclassify</strong> buttons still work for single actions. "
        "All deletions land in <code>~/.Trash</code> (recoverable from "
        "Finder) and log to <code>.classify_deletions.log</code> / <code>"
        ".classify_reclassifications.log</code> in the vault root."
        "</div>"
    )
    cards.append(
        f'<div class="summary">{len(queue)} notes need manual review. '
        "Click a note title to open it in Obsidian.</div>"
    )
    cards.append(
        '<div class="select-controls">'
        '<button type="button" onclick="selectAllVisible()">Select all</button>'
        '<button type="button" onclick="clearSelection()">Clear selection</button>'
        '</div>'
    )
    cards.append(
        '<div class="selection-toolbar" id="selection-toolbar" hidden>'
        '<span class="selection-count">'
        '<strong id="selection-count">0</strong> selected</span>'
        '<button type="button" onclick="clearSelection()">Clear</button>'
        '<button type="button" class="danger" onclick="doDeleteSelected()">'
        'Delete selected</button>'
        '</div>'
    )
    for item in queue:
        note_path: Path = item["path"]
        rel = _relative_to_vault(note_path, vault)
        rel_str = str(rel)
        url = _obsidian_url(vault_name, rel)
        conf = float(item["confidence"])
        klass = _confidence_class(conf)
        excerpt = _body_excerpt(note_path)
        # JS string-escape the path for the inline onclick handlers.
        js_path = (
            rel_str.replace("\\", "\\\\").replace("'", "\\'").replace("\n", "")
        )
        proposed_type = str(item.get("proposed_type", "?"))
        proposed_org = str(item.get("proposed_org", "?"))

        # HTML-attribute-escape the path for the data-path attribute.
        attr_path = html.escape(rel_str, quote=True)
        cards.append(
            f'<article class="card">'
            f'  <div class="card-head">'
            f'    <input type="checkbox" class="select-checkbox" '
            f'data-path="{attr_path}" onchange="onSelectionChange()" '
            f'aria-label="Select this note">'
            f'    <a href="{html.escape(url, quote=True)}">'
            f'{html.escape(rel_str)}</a>'
            f'    <span class="confidence {klass}">{conf:.2f}</span>'
            f'  </div>'
            f'  <div class="fields">'
            f'    <span><strong>type:</strong> {html.escape(proposed_type)}</span>'
            f'    <span><strong>org:</strong> {html.escape(proposed_org)}</span>'
            f'  </div>'
            f'  <div class="reason">{html.escape(str(item.get("reason", "")))}</div>'
            + (
                f'  <pre class="excerpt">{html.escape(excerpt)}</pre>'
                if excerpt else ""
            )
            + f'  <div class="actions">'
            f'    <button class="danger" '
            f'onclick="doDelete(this.closest(\'.card\'),\'{js_path}\')">'
            f'Delete</button>'
            f'    <button '
            f'onclick="doReclassify(this.closest(\'.card\'),\'{js_path}\')">'
            f'Reclassify…</button>'
            f'    <button class="quick" '
            f'onclick="doReclassify(this.closest(\'.card\'),\'{js_path}\','
            f'\'reference\',\'Personal\')">'
            f'Quick: reference / Personal</button>'
            f'    <button class="quick" '
            f'onclick="doReclassify(this.closest(\'.card\'),\'{js_path}\','
            f'\'technical\',\'Amazon\')">'
            f'Quick: technical / Amazon</button>'
            f'  </div>'
            f'</article>'
        )

    return _HTML_SHELL_WITH_JS.format(
        title=html.escape(title), css=css, meta=meta,
        body="".join(cards), js=_ACTIONS_JS,
    )


def render_sample_html(samples: list[Path], vault: Path) -> str:
    """Render a random sample of classified notes as HTML for spot-checking."""
    vault_name = vault.name
    title = "Classification Sample"
    meta = (
        f"{len(samples)} notes &middot; vault: {html.escape(vault_name)}"
    )

    if not samples:
        body = (
            '<div class="empty">'
            "No classified notes matched the filter."
            "</div>"
        )
        return _HTML_SHELL.format(
            title=html.escape(title), css=_CSS, meta=meta, body=body
        )

    cards: list[str] = []
    cards.append(
        '<div class="summary">'
        "Click a note title to open it in Obsidian. The confidence badge "
        "shows the classifier's own self-rated certainty."
        "</div>"
    )
    for path in samples:
        fm = read_frontmatter(path)
        rel = _relative_to_vault(path, vault)
        url = _obsidian_url(vault_name, rel)
        conf = float(fm.get("classify_confidence", 0.0) or 0.0)
        klass = _confidence_class(conf)
        excerpt = _body_excerpt(path)

        # Build the fields strip in a defined order.
        fields_html: list[str] = []
        for label, key in [
            ("type", "type"), ("org", "org"), ("context", "context"),
            ("up", "up"),
        ]:
            value = fm.get(key)
            if value is not None:
                fields_html.append(
                    f'<span><strong>{label}:</strong> '
                    f'{html.escape(str(value))}</span>'
                )
        if fm.get("people"):
            fields_html.append(
                f'<span><strong>people:</strong> '
                f'{html.escape(", ".join(str(p) for p in fm["people"]))}</span>'
            )
        if fm.get("tags"):
            fields_html.append(
                f'<span><strong>tags:</strong> '
                f'{html.escape(", ".join(str(t) for t in fm["tags"]))}</span>'
            )

        cards.append(
            '<article class="card">'
            f'  <div class="card-head">'
            f'    <a href="{html.escape(url, quote=True)}">'
            f'{html.escape(str(rel))}</a>'
            f'    <span class="confidence {klass}">{conf:.2f}</span>'
            f'  </div>'
            f'  <div class="fields">{"".join(fields_html)}</div>'
            + (
                f'  <pre class="excerpt">{html.escape(excerpt)}</pre>'
                if excerpt else ""
            )
            + '</article>'
        )

    return _HTML_SHELL.format(
        title=html.escape(title), css=_CSS, meta=meta, body="".join(cards)
    )
