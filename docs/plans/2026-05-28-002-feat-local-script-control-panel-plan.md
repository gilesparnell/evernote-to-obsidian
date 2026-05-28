---
title: "feat: Local script control panel"
type: feat
status: completed
date: 2026-05-28
---

# feat: Local script control panel

## Routing Summary

| Runner | Units | Total |
|--------|-------|-------|
| claude | 1, 2, 3, 4 | 4 |

All claude — the project's `docs/decisions/decisions.md` (2026-05-14) records that codex-delegate round-trips produced no files on disc in this environment, so all units stay on claude until that's diagnosed. The async job-manager (Unit 2) also has real concurrency/subprocess judgement calls that warrant Claude.

---

## Problem Frame

The classifier toolkit has grown to ~8 operator scripts (`classify_vault`, `audit_manifest`, `sample_classified`, `audio_link_fix`, `strip_redundant_titles`, `migrate_vault`, `review_server`, plus `export_granola` in the sibling granolaSync repo). Each is a CLI with its own flags. The operator — mid-workflow, often days between sessions — struggles to remember:
- Which script does what
- When they'd reach for each one
- The exact invocation

Now that the bulk migration is largely done, the day-to-day need is a small set of recurring tools (classify new notes, audit deletions, spot-check, trigger Granola), while the one-time migrations (`audio_link_fix`, `strip_redundant_titles`) are effectively retired. The operator wants a **single page** that surfaces this, prioritised, with **one-click execution** and **completion status**.

### Architecture constraint (resolved 2026-05-28)

The operator initially asked for a Vercel deployment. **That is architecturally impossible**: every script requires local filesystem access (the Obsidian vault), the local LM Studio server (`localhost:1234`), and the project venv. Vercel's cloud serverless functions have none of these. Operator confirmed the pivot to a **local web app** — a `127.0.0.1`-bound server that serves the dashboard AND executes scripts via subprocess, exactly the pattern `scripts/classify/review_server.py` already uses. This also keeps vault-deleting scripts off the public internet (a security win).

---

## Proposed Solution

A new local server `scripts/classify/control_panel.py`, a sibling to `review_server.py`, built on three testable pieces:

1. **Script registry** (`script_registry.py`) — declarative allowlist of runnable scripts with metadata (name, use-case, priority tier, interpreter, cwd, default args). The allowlist is the security boundary: the panel can ONLY run registry entries, never arbitrary commands. `POST /run` takes a registry KEY, never a command string.

2. **Job manager** (`JobManager` class) — async subprocess execution. Scripts like `classify_vault` run for hours, so execution cannot block the HTTP request. `start_job(key)` spawns `subprocess.Popen`, captures stdout+stderr, returns a `job_id` immediately; a background thread tracks state (`running` → `complete`/`failed` + exit code + captured output). One job at a time for v1 (rejects a new run while one is active — prevents two `classify_vault` runs racing on the vault).

3. **HTTP server** (`control_panel.py`) — `127.0.0.1` only, stdlib `http.server`. `GET /` renders the catalogue grouped by priority tier; `POST /run` (key) starts a job; `GET /status/<job_id>` returns state + output for the page to poll.

### Architecture sketch

```
┌──────────────────────────────────────────────────────────────┐
│  control_panel.py   (127.0.0.1:<port>, stdlib http.server)    │
│                                                                │
│  GET  /            → render_catalog(registry, job_manager)     │
│  POST /run         → {key} → job_manager.start_job(key) → id   │
│  GET  /status/<id> → job_manager.get_status(id) → JSON         │
│  GET  /health      → ok + version                              │
└───────────┬───────────────────────────┬──────────────────────┘
            │                           │
            ↓                           ↓
   ┌──────────────────┐      ┌─────────────────────────────┐
   │ script_registry  │      │  JobManager                 │
   │ (allowlist data) │      │  start_job(key)->job_id     │
   │  key, name,      │      │  get_status(id)->dict       │
   │  use_case, tier, │      │  subprocess.Popen + thread  │
   │  interpreter,    │      │  capture stdout/stderr      │
   │  cwd, argv       │      │  one job at a time (v1)     │
   └──────────────────┘      └─────────────────────────────┘
```

### Priority tiers in the catalogue

| Tier | Scripts | Rationale |
|---|---|---|
| **Daily / now** | `classify_vault` (dry-run + real), `audit_manifest`, `sample_classified`, `export_granola` (manual Granola trigger) | The ongoing loop now that migration is done — classify new notes, check deletions, spot-check, pull Granola meetings on demand |
| **Occasional / upcoming** | `migrate_vault` (dry-run + confirm) | The next big step: split work/personal notes to the Business vault. Not yet run. |
| **Done / archived** | `audio_link_fix`, `strip_redundant_titles` | One-time migrations, complete. Kept runnable for the rare new-import case, but visually de-emphasised. |
| **Link-out** | `review_server` | Itself a long-running server. v1 shows the launch command + a link to `localhost:8765` rather than managing its lifecycle (see Out of Scope). |

### Argument handling (v1)

Each registry entry carries a fixed `argv` (with `--vault` pinned to the Personal vault from a config constant). Destructive/long scripts get **two entries** — a `--dry-run` variant and a real variant — rather than free-form arg input. This keeps the security surface tiny (no user-supplied shell) and matches how the operator actually runs them. Free-form args (custom `--folder`, `--limit`) are Out of Scope for v1.

---

## System-Wide Impact

- **Interaction graph**: `POST /run` → `JobManager.start_job` → `subprocess.Popen([interpreter, script, *argv])` → background thread drains stdout/stderr into an in-memory buffer → state flips to `complete`/`failed` on process exit. The page polls `GET /status` every ~1.5s.
- **Error propagation**: subprocess non-zero exit → job state `failed` + captured stderr in the output buffer + exit code surfaced. Server never crashes on a failed job. `Popen` spawn failure (e.g. bad interpreter path) → caught, job state `failed` with the exception message.
- **State lifecycle risks**: in-memory job store (single-process, single-user, local — no DB). Jobs lost on server restart; acceptable (no long-term history requirement). One-job-at-a-time guard prevents two `classify_vault` runs corrupting the vault concurrently.
- **API surface parity**: mirrors `review_server.py`'s conventions (127.0.0.1 bind, JSON responses, `/health`). Does NOT share code initially (premature) but follows the same shape; a future refactor could extract a shared HTTP base.
- **Integration test scenarios**: (1) start panel → GET / returns catalogue HTML with all tiers; (2) POST /run a fast safe script → poll status → running then complete with captured output; (3) POST /run a failing script → status `failed` + exit code; (4) POST /run while a job is active → rejected with a clear message; (5) POST /run an unknown key → 400, no subprocess spawned.

---

## Units

### Unit 1: Script registry + catalogue HTML rendering
**Execution target: claude**

#### Tasks (tests first)
- `scripts/classify/script_registry.py`:
  - `SCRIPTS: list[dict]` — each entry: `key`, `name`, `use_case`, `tier` (`daily`/`occasional`/`done`/`link`), `interpreter` (venv python or system python3 for granola), `cwd`, `argv` (list), optional `dry_run_of` linkage.
  - `validate_registry()` → raises on missing keys / duplicate keys / nonexistent script paths. Run at import.
  - `by_tier()` → `{tier: [entries]}` ordered for display.
- `render_catalog(registry, job_states) -> str` — self-contained dark-theme HTML (mirror `html_renderer.py` aesthetic). Cards grouped by tier, each with name, use-case, Run button (`data-key`), and a status slot. Done-tier cards visually de-emphasised.

#### Tests (`tests/unit/classify/test_script_registry.py`, `test_control_panel_render.py`)
- registry: every entry has required keys; keys unique; every `argv[0]`/script path exists on disc; `by_tier` groups + orders correctly.
- render: HTML contains every script name; cards grouped under tier headings; Run buttons carry the right `data-key`; a running job shows its status; HTML is well-formed (balanced tags via a basic check).

#### Verification gate
`scripts/classify/venv/bin/pytest tests/unit/classify/test_script_registry.py tests/unit/classify/test_control_panel_render.py -v` — green. Full suite no regressions.

---

### Unit 2: JobManager — async subprocess execution + status
**Execution target: claude**

#### Tasks (tests first)
- `JobManager` (in `control_panel.py` or a `job_manager.py` module):
  - `start_job(key) -> job_id` — looks up registry entry, spawns `subprocess.Popen([interpreter, *argv], cwd=..., stdout=PIPE, stderr=STDOUT)`, starts a daemon thread draining output into a buffer, records `started_at`. Raises if a job is already running (one-at-a-time) or key unknown.
  - `get_status(job_id) -> dict` — `{state: running|complete|failed, exit_code, output, started_at, key}`.
  - `is_busy() -> bool`.

#### Tests (`tests/unit/classify/test_job_manager.py`)
- Use a trivial fast command (e.g. a registry test-double pointing at `python -c "print('hi')"`) so tests don't touch the real vault:
  - start → status transitions running → complete; exit_code 0; output contains "hi".
  - a command that exits non-zero → state `failed`, exit_code != 0, stderr captured.
  - start while busy → raises / rejected.
  - unknown key → raises.
  - output capture for multi-line stdout.

#### Verification gate
`pytest tests/unit/classify/test_job_manager.py -v` — green. No real scripts invoked in tests.

---

### Unit 3: control_panel.py HTTP server + CLI entry
**Execution target: claude**

#### Tasks (tests first)
- `_Handler(BaseHTTPRequestHandler)` with `do_GET` (`/`, `/health`, `/status/<id>`) and `do_POST` (`/run`). 127.0.0.1 bind. JSON bodies. Mirror `review_server.py` safety conventions.
- `start_server(port) -> HTTPServer`, `main()` CLI with `--port` (default e.g. 8770, distinct from review_server's 8765), `--vault`.
- Rich `--help` per project convention.

#### Tests (`tests/integration/classify/test_control_panel.py`)
- Live-server integration (same pattern as `test_review_server.py`): boot on an ephemeral port, then:
  - `GET /health` → 200 + version.
  - `GET /` → 200, HTML contains catalogue + every tier.
  - `POST /run` {key: <fast test key>} → 200 + job_id; poll `GET /status/<id>` → eventually complete.
  - `POST /run` unknown key → 400, no spawn.
  - `POST /run` while busy → 409 with clear message.

#### Verification gate
`pytest tests/integration/classify/test_control_panel.py -v` — green. Full suite green.

---

### Unit 4: Smoke test + version bump + CHANGELOG + docs
**Execution target: claude**

#### Tasks
1. **Manual smoke** (operator-runnable): start the panel, open `http://localhost:8770`, run a fast SAFE script (`audit_manifest --dry-run` or `sample_classified --n 5`), watch running → complete + output render. Confirm no real vault mutation from the smoke.
2. Version bump `pyproject.toml` (minor — new CLI/feature). CHANGELOG entry (What's new: "a local control panel page lists every tool, prioritised, with one-click run + status"; Under the hood: the three modules + tier design + 127.0.0.1 security).
3. Docs: add the panel to `docs/2026-05-26-post-chunk-operator-checklist.md` (how to launch it) and a line in `docs/RUNBOOK.md`. Optionally a card on the docs `index.html` per the Project Documentation Standard.
4. Operator gate: panel is launched manually (`runner=human` discipline) — the plan does not auto-start a server.

#### Verification gate
Full suite green; manual smoke shows a real job running → completing in the browser; version + CHANGELOG updated.

---

## Out of Scope (v1)

- **Vercel / any cloud deployment** — architecturally impossible (local filesystem + LM Studio + venv). Local only.
- **Free-form argument input** (custom `--folder`/`--limit` from the page) — v1 uses fixed presets + dry-run/real variants. Free-form args would widen the security surface and add UI complexity.
- **Concurrent multi-job execution** — one job at a time in v1. (Different scripts CAN safely run together, e.g. audit during classify, but enforcing safe-combination rules is more than v1 needs.)
- **Managing `review_server`'s lifecycle** — v1 shows its launch command + a link to `localhost:8765`. Full start/stop server management (a "server" job type with a Stop button) is deferred.
- **Persisting job history across restarts** — in-memory only.
- **Auth** — `127.0.0.1` bind + single local user is the security model, same as `review_server`.
- **Scheduling** — launchd already handles Granola; cron-style scheduling is out.

---

## Acceptance Criteria

- [ ] `script_registry.py` lists all 8 scripts with key/name/use-case/tier; `validate_registry()` passes; nonexistent script paths fail validation
- [ ] Catalogue page renders cards grouped by tier (daily / occasional / done / link), done-tier de-emphasised
- [ ] `JobManager` runs a subprocess async, captures output, tracks running→complete/failed + exit code, enforces one-at-a-time
- [ ] `POST /run` accepts only registry keys (no arbitrary commands); unknown key → 400; busy → 409
- [ ] `GET /status/<id>` returns live state the page polls; completed job shows captured output
- [ ] 127.0.0.1 bind only
- [ ] Manual smoke: a real safe script runs from the browser and shows completion
- [ ] Full test suite green (unit: registry, render, job-manager; integration: live server)
- [ ] Version bumped + CHANGELOG entry + docs updated

## Final Verification

1. `scripts/classify/venv/bin/pytest -q` — full suite green
2. Manual browser smoke: panel loads, catalogue grouped by tier, run `audit_manifest --dry-run` → running → complete + output, no vault mutation
3. Security check: `POST /run` with a non-registry command string is rejected; server bound to 127.0.0.1 only (`lsof -iTCP:8770` shows 127.0.0.1)
4. `pyproject.toml` bumped; CHANGELOG entry present; checklist + RUNBOOK reference the panel

## Sources & References

- Internal pattern: `scripts/classify/review_server.py` (127.0.0.1 stdlib server, `do_GET`/`do_POST`, `InvalidPath` safety, `test_review_server.py` live-server test pattern)
- Internal: `scripts/classify/html_renderer.py` (dark-theme self-contained HTML aesthetic to mirror)
- Script inventory: `scripts/classify/{classify_vault,audit_manifest,sample_classified,audio_link_fix,strip_redundant_titles,migrate_vault,review_server}.py` + `../granolaSync/export_granola.py`
- Convention: project CLAUDE.md (venv pytest, tdd-first, atomic writes, Versioning Discipline, Project Documentation Standard)
