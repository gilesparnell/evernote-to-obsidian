# Decisions Log

Project-local tactical decisions made during plan execution. Newest at top. Promote to a cross-project ADR only when impact extends outside this project.

---

## 2026-05-28 AEST — Control panel version read from pyproject.toml, surfaced in /health + UI

Unit 4 (finalisation) wired the running version into the control panel per the global Versioning Discipline (a `/health` endpoint that exists MUST report the version, and the version must be visible somewhere persistent in-app). `control_panel.py` now reads `__version__` from `pyproject.toml` via `tomllib` at import — single source of truth, no duplicated constant — and surfaces it in both `GET /health` (`{"ok", "version", "vault"}`) and the brand tag (`Operator Console · v0.6.0`). Tests written first per tdd-first: `test_health_reports_version` (integration) + `test_shows_version` (render). Bumped 0.5.0 → 0.6.0 (minor — new CLI/feature).

## 2026-05-28 AEST — Control panel is LOCAL, not Vercel

Operator asked for a Vercel-deployed web app to run the toolkit scripts. Rejected Vercel as architecturally impossible: every script needs the local Obsidian vault, the local LM Studio server (`localhost:1234`), and the project venv — none of which exist in Vercel's cloud serverless runtime. Built a `127.0.0.1`-bound stdlib `http.server` instead (sibling to `review_server.py`), which also keeps the vault-deleting scripts off the public internet. Security boundary: `POST /run` accepts a registry KEY from `script_registry.py`'s allowlist, never a command string — no arbitrary command execution. See plan `docs/plans/2026-05-28-002-feat-local-script-control-panel-plan.md`.

## 2026-05-28 AEST — Control panel UI matches SprintTracker, not "Deep Ocean Tech"

First two UI attempts used the global "Deep Ocean Tech" language (teal `#38bfa0`, Satoshi/Outfit, glass cards). Operator rejected both as not production-grade, then pointed at `parnell-systems/sprint-tracker/` as the reference. Replicated SprintTracker's actual system instead: green-500 `#22c55e` accent on grey-950 `#030712`, grey-900 cards, grey-800 borders, Geist + Geist Mono, shadcn `rounded-xl` nav with `green-500/10` active state, green icon-square brand. Tokens lifted from `sprint-tracker/src/app/globals.css` + the dashboard `sidebar-nav-link.tsx`. **Do not revert to teal** — that look was explicitly rejected twice. Note: this means the project now has TWO design languages — Deep Ocean for the docs/GitHub-Pages site (per global CLAUDE.md), SprintTracker-green for the operator control panel. They are deliberately separate.

## 2026-05-28 AEST — Async one-job-at-a-time execution model for the control panel

`classify_vault` runs for hours, so the control panel cannot block the HTTP request on subprocess completion. `JobManager.start_job` spawns `subprocess.Popen`, returns a job_id immediately, and a daemon thread drains stdout/stderr into an in-memory buffer; the page polls `GET /status/<id>`. Enforced ONE job at a time (raises on a second concurrent `start_job`) so two `classify_vault` runs can't race on the vault. In-memory job store only — jobs are lost on server restart, which is acceptable (no history requirement). Free-form argument input was deferred; destructive/long scripts instead get two fixed registry entries (a `--dry-run` variant and a real variant). See plan §Out of Scope.

---

## 2026-05-26 AEST — New `clipping` type + `[[Clippings]]` MOC, not re-used `[[Reference]]`

Body-shape rules (single image / URL / audio / PDF embed) produce a new R2 `type` value `clipping` mapped to a new `[[Clippings]]` MOC, rather than reusing the existing `[[Reference]]` MOC. Operator chose separation because: (a) `[[Reference]]` is for operator-authored knowledge — RFCs, cheatsheets, summaries — and mixing 300+ Evernote import artefacts would dilute that, (b) keeping clippings separate makes them easy to bulk-prune in Obsidian's graph view (most pre-2020 Skitch screencaps have no recent reference value), (c) reversing later is trivial (one entry in `UP_MAP`) whereas un-mixing later requires per-note retagging. One `UP_MAP` entry added to `scripts/classify/moc_map.py`; Obsidian auto-stubs `Clippings.md` on first wikilink resolution. See plan §"Type / MOC decisions".

## 2026-05-26 AEST — Tiny bodies (< 30 stripped chars) hard-delete, no quarantine folder

When the rules cascade can't classify a body with confidence ≥ 0.80 AND the body has < 30 chars of semantic content (after stripping markdown wrappers), the file is hard-deleted via `os.unlink()` on the spot. Operator opted in explicitly on 2026-05-26 over the "move to `_trash_YYYY-MM-DD/` then manually purge" quarantine pattern. Reason: the operator's project north-star (per `project_north_star.md`) is to end with a curated vault, not an archive — and most of these files (phone numbers, IDs, address fragments, one-line scribbles) are obviously junk that no triage step would change the verdict on. Every deletion is recorded in `<vault>/.classify_deleted_manifest.json` with path + stripped char count + 50-char body preview + AEST timestamp + run_id, providing an audit trail. Recovery, if ever needed, is from the pre-classification backup tarball at `~/Backups/`. First run produced 62 deletions, of which 5 had filenames that suggested work-relevance (`Peer Feedback - 2015`, `Best Practices Discussion with Fran`, etc.) — flagged in the 2026-05-26 handoff entry for operator review. See plan §"Type / MOC decisions".

## 2026-05-26 AEST — Pipeline ordering: rules cascade FIRST, then purge gate, then LM

In `classify_vault.py`'s per-note loop, the new ordering is: (1) `rules_classifier.classify()` first — body-shape rules inside it catch clipping shapes with conf 0.85; (2) if rules return conf < 0.80, check `should_purge_by_body_shape(body)` — purge if true, short-circuit before LM; (3) else LM fallback. The naïve ordering (purge gate before rules) would have wrongly deleted image-only short bodies, because their strip-length is near zero (`![x](path.png)` strips to about `!xpath.png`, < 30 chars). Test `TestBodyShapeOrdering::test_image_only_short_body_classifies_as_clipping_not_deleted` locks in this ordering. The MIN_BODY_LENGTH = 50 "too short to classify" review-queue path is preserved for 30–49 char bodies that escape both the clipping rules and the purge gate.

## 2026-05-26 AEST — Test body length not classifier behaviour: six pre-existing tests updated, not relaxed

Six tests in `tests/integration/classify/test_classify_vault.py` failed after the purge gate landed because they used 4–15 char convenience bodies (e.g. "short body 1", "tiny", "also tiny") to test things like checkpoint writes, directory skipping, review-queue rendering — none of which are actually about tiny bodies. Updated the test bodies to clear the 30-char purge threshold rather than weakening the new purge behaviour. The one test that genuinely tests "short body → review queue" (`test_short_body_goes_to_review_with_too_short_reason`) was updated to use a 38-char body — exercising the preserved "too short" review-queue path for the 30–49 char band. This is per the tdd-first skill's anti-pattern: "Do not weaken assertions to make tests pass".

## 2026-05-26 AEST — Markdown-wrapped tel links survive the purge gate (known v2 gap)

The strip regex `_BODY_STRIP_MARKDOWN_RE = re.compile(r"[*_#>\[\]()\\\n\t]")` strips markdown structural chars but NOT URL contents inside `(...)`. So a body like `[041 581 7988](tel:041%20581%207988)` strips to `041 581 7988tel:041%20581%207988` (32 chars) and survives to the review queue rather than purging. Documented gap in the 2026-05-26 plan §Out of Scope and CHANGELOG `[0.3.0]` Under-the-hood notes. v2 enhancement: smarter strip that collapses `[text](url)` to just `text` before counting. Workaround for now: manually delete via the helper-server UI when these surface in the review HTML.

## 2026-05-14 AEST — Units 4–8 executed by Claude despite codex-delegate tags

Plan tagged Units 4, 5, 6 as `codex-delegate`. Two attempted Codex round-trips (Unit 3 + Unit 4) both reported done but produced no files on disc — every expected path was missing across the entire user filesystem. Without seeing Codex's actual session output, the failure mode couldn't be diagnosed. User explicitly chose to keep work in Claude for the remainder of the plan. Recording the override so future planning doesn't keep routing units to a tool that's not functioning in this setup. Codex routing should be re-evaluated only after the underlying issue is found (sandbox? wrong working directory? plan mode?). See handoff log 2026-05-14 entries.

## 2026-05-14 AEST — Run classify tests via venv pytest, not bare pytest

Bare `pytest` (Homebrew formula at `/opt/homebrew/bin/pytest`) uses a locked libexec Python with no `pip` binary, so PyYAML can't be installed into it. The classify package depends on PyYAML, so its tests can't run under bare pytest. Resolution: `pytest>=8.0` added to `scripts/classify/requirements.txt`, and classify tests are invoked via `scripts/classify/venv/bin/pytest`. This venv-pytest also runs the existing 102 tests cleanly (they have no extra dependencies), so it is now the single command for the whole suite. Bare `pytest` still works for the existing tests but will skip-collect the classify tests with a yaml ImportError. Plan §Unit 2 verification gate updated.

## 2026-05-14 AEST — LM Studio `tool_choice` requires string form, not object

LM Studio's OpenAI-compatible chat-completions endpoint rejects the object-form `tool_choice={"type":"function","function":{"name":"..."}}` with HTTP 400 (`Invalid tool_choice type: 'object'`). Only string values `none`/`auto`/`required` are accepted. Verified during Unit 0 smoke test against `google/gemma-4-e4b`. Implementation impact: Unit 4 (`lm_classifier.py`) must call the OpenAI SDK with `tool_choice="required"`. With a single tool exposed, this is functionally identical to forcing the named function. See `docs/plans/2026-05-13-001-feat-obsidian-knowledge-graph-beta-plan.md` §Unit 4 (updated 2026-05-14).

## 2026-05-14 AEST — Classifier code lives in `evernote-to-obsidian/`, not granolaSync

Option B chosen over the original plan layout (which placed new classifier code in `granolaSync/classify/`). Reason: the new code *extends* `evernote-to-obsidian/scripts/classify_notes.py`, and splitting it across repos creates a cross-repo import dependency and a second `git init` overhead. Only Unit 6 (Granola export schema additions) stays in granolaSync because it modifies `export_granola.py` which lives there. Plan doc was path-rewritten and a `## Path Layout` section added. See plan §Path Layout.
