---
title: "feat: Control panel — server lifecycle, console Obsidian links, readability"
type: feat
status: completed
date: 2026-05-28
---

# feat: Control panel — server lifecycle, console Obsidian links, readability

## Routing Summary

| Runner | Units | Total |
|--------|-------|-------|
| claude | 1, 2, 3, 4 | 4 |

All claude — the `docs/decisions/decisions.md` (2026-05-14) note records codex-delegate
round-trips produced no files on disc in this environment, so units stay on claude.

## Problem Frame

Operator feedback on the Obsidian Vault Control Panel (v0.6.1):
1. Explanatory text is hard to read — the secondary greys are below WCAG AA on the dark bg.
2. The review/triage server is display-only (a launch command); operator wants Start/Stop from the panel.
3. After "Classify vault (apply)" the operator wants to click a note name and have it open in Obsidian.

Investigation findings:
- Readability: `.detail .use` is grey-400 (`#9ca3af`); sidebar `.tool-desc` is grey-600 (`#4b5563`, ~2.5:1) and ellipsis-truncated.
- Server: `review-server` registry entry is tier `link` with NO interpreter/argv — display only. The JobManager runs one-shot jobs (waits for exit), one at a time; no terminate path.
- Obsidian links: `classify_vault` (apply) prints only a tqdm bar + an aggregate summary; per-note results go to `classification-review.html`. No note names in console output. Operator chose: add per-note logging + linkify vault `.md` paths in the console.

## Units

### Unit 1: Readability + use-case layout (CSS)
**Execution target: claude** — presentation only, no logic; verify visually.

- Raise contrast in `_PAGE_CSS`: `.detail .use` → grey-200; `.tool-desc` → grey-300/400 with 2-line clamp (drop single-line ellipsis); `.cmd-label`, `.run-hint`, `.tier-sub`, `.tool-name` (idle) lifted to ≥ grey-400. Keep green accent + dark surfaces.
- Ensure the use-case sits clearly beneath the tool name in both the detail pane (h2 → use) and sidebar (name → wrapped desc).
- No new logic → no unit test; verify with a browser screenshot (frontend-design discipline). Existing render tests must stay green.

### Unit 2: Server lifecycle in JobManager (logic — TDD)
**Execution target: claude**

- `script_registry.py`: make `review-server` runnable as a server — add `interpreter` (venv py), `cwd` (repo root), `argv` (`review_server.py --vault <Personal> --port 8765`), `url` (`http://localhost:8765`), `kind: "server"`. Keep tier `link` (renders under "Servers"). `validate_registry`: a `kind == "server"` entry requires interpreter/cwd/argv/url and its script must exist.
- `JobManager`: server processes tracked separately from the one-shot slot.
  - `start_server(key, entry) -> dict` — spawn `Popen`, store in `self._servers[key]`; does NOT set `_active_id`. Raise/return-existing if already running for that key.
  - `stop_server(key)` — `terminate()`, escalate to `kill()` after a short grace; mark stopped.
  - `server_status(key) -> {state: running|stopped, pid, url}`.
  - `is_busy()` and `start_job` unaffected by servers (a running server must not block classify).
- Tests (`tests/unit/classify/test_job_manager.py`): start tracks + running; stop terminates + stopped; start-when-running; stop-when-stopped; a running server does not block `start_job`. Use `python -c "import time; time.sleep(30)"` as the server test-double.

### Unit 3: Server endpoints + Start/Stop/Open UI (integration + render — TDD)
**Execution target: claude**

- HTTP: `POST /server/start` {key} → starts + returns state; `POST /server/stop` {key} → stops; `GET /server/status/<key>` → state. Unknown/ non-server key → 400.
- UI: for `kind == "server"` entries, the detail pane shows **Start** + **Stop** buttons and an **Open** link (`href=url`) instead of Run; buttons reflect running state.
- Tests: integration (`test_control_panel.py`) start→status running→stop→status stopped, unknown key → 400; render (`test_control_panel_render.py`) server entry exposes start/stop controls + url.

### Unit 4: Per-note logging + console Obsidian linkify (logic — TDD)
**Execution target: claude**

- `classify_vault.py`: add `--log-notes` flag; when set, print one line per processed note: `<decision>\t<relpath>[\t-> <type>]` (decision ∈ `auto`/`review`/`purged`), relpath = path relative to vault root. Registry `classify-run` argv gains `--log-notes`. Default off so other callers/tests are unaffected.
- `control_panel.py`: pure `linkify_console_output(text, vault_name) -> str` — HTML-escape the text, then wrap any vault-relative `*.md` path token in `<a href="obsidian://open?vault=<vault>&file=<urlencoded>">`. `/status` returns an extra `output_html` field; the page sets `consoleBody.innerHTML = output_html` (escaped-then-linkified, so no XSS).
- Tests: `test_classify_vault.py` — `--log-notes` prints one line per note with decision + relpath (and is silent without the flag). `test_control_panel_render.py`/new — `linkify_console_output`: a `.md` path → obsidian anchor; plain text → escaped, unchanged; HTML-special chars escaped; spaces in path percent-encoded.

## Out of Scope
- Concurrent multi-job execution (servers excepted) — still one one-shot job at a time.
- Managing arbitrary servers — only the registered review server for now.
- Persisting server/job state across panel restarts.

## Acceptance Criteria
- [ ] Explanatory text passes WCAG AA on the dark bg; sidebar descriptions readable (not truncated to a faint ellipsis)
- [ ] Review server starts/stops from the panel; running server doesn't block classify; Open link works
- [ ] `classify_vault --log-notes` prints per-note decisions; console renders vault `.md` paths as clickable `obsidian://` links
- [ ] Full suite green; visual screenshot confirms readability + server controls

## Final Verification
1. `scripts/classify/venv/bin/pytest -q` — full suite green
2. Browser screenshot: explanatory text legible; server entry shows Start/Stop/Open; a classify run shows clickable note links
3. Version bump + CHANGELOG; handoff updated
