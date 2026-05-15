# Changelog

All notable changes. Bumped on every PR that ships behaviour change.

## Conventions
- patch (`0.0.x`) — bug fixes, copy tweaks, dependency bumps
- minor (`0.x.0`) — new features, new CLIs, new tracked events
- major (`x.0.0`) — breaking changes (CLI signature, frontmatter schema, vault path layout)

Each entry is split into:
- **What's new** — customer-facing outcomes (the operator's day-to-day)
- **Under the hood** — technical detail (paths, function names, why)

---

## [0.2.0] — 2026-05-15

### What's new
- **In-browser triage with one-click delete + reclassify.** New helper server reads the review queue and serves it back with action buttons on every card — no more leaving the page to fix a misclassification. Deletes go to macOS Trash (recoverable via Finder), not `rm`. Both actions append to per-vault audit logs.
- **Rules cascade catches more AWS notes for free.** Five new title-pattern rules (AWS service prefixes, Evernote web-clip "Cursor and …" titles, GoToWebinar viewer captures, "Inbox – email" exports, camera-export numeric filenames). Expected ~32% cut to the chunk-3-shape review queue on the next chunk — every match lifts a note from "burns 8 s of LM time + might land in review queue" to "instant, free, auto-classified".
- **One-shot title quoter for malformed Evernote YAML.** Applied across 1,540 AWS notes; the pipeline no longer crashes on raw `title: 1-1: Foo` lines.
- **HTML review outputs** with click-through `obsidian://` links — review queue and post-run samples both open in any browser.
- **Operator-reference page** on the docs site covering every CLI flag and every progress-bar field, plus three decision gates for when to stop and tune.
- **Long batches survive concurrent triage.** Files deleted or renamed mid-run no longer kill the chunk — they're silently skipped and surfaced as `missing:N` in the progress bar.

### Under the hood
- New module `scripts/classify/review_server.py` (~360 lines). stdlib `http.server`, 127.0.0.1-only bind, every client-supplied path resolved against `--vault` root (`InvalidPath` raised on traversal escape). Endpoints: `GET /health`, `GET /`, `POST /delete`, `POST /reclassify`. Trash goes to `~/.Trash/evernote-cleanup-<YYYY-MM-DD>/` with paired `_resources/` folder. 20 tests including live-server integration per endpoint.
- `scripts/classify/rules_classifier.py`: 5 new entries appended to `_TITLE_TYPE_RULES` covering AWS service prefixes, Cursor web-clipper, GoToWebinar, Inbox email exports, and `\d{8,}\.(jpg|png|heic|gif)` camera-export filenames. Each anchored to start with `(?:\b|_)` boundary to absorb Evernote's underscore-as-colon substitution. 18 new tests in `TestReviewQueueMinedRules`.
- `scripts/classify/classify_vault.py`: pre-scan (`_count_already_classified`) and main loop body both wrap file IO in `try/except FileNotFoundError → skip`. New `skipped_missing` counter threaded through tqdm postfix (`missing:N` segment), `.classify_progress.json` heartbeat (`totals.skipped_missing`), summary dict, and CLI summary print.
- `scripts/classify/lm_classifier.py`: `openai.OpenAI()` cached via `@functools.lru_cache(maxsize=1)` — fixes the FD leak that crashed runs at ~297 LM calls. Side effect: LM avg dropped 18.7 s → 8.4 s from connection-pool reuse.
- `scripts/classify/frontmatter.py`: `_split()` catches `yaml.YAMLError` so unquoted titles don't crash the pipeline. Same defence flows through `read_frontmatter` / `is_classified` / `write_frontmatter`.
- `scripts/classify/html_renderer.py`: adds `render_review_queue_html_with_actions` and `parse_review_queue_md` for the review server's GET /. Self-contained dark theme. New action-button CSS + vanilla-JS POST handlers.
- New CLIs: `scripts/classify/fix_evernote_titles.py`, `scripts/classify/sample_classified.py` (with `--html`), `scripts/classify/review_server.py`.
- Docs: `docs/operator-reference.html` (single-page reference for every CLI flag and progress-bar field), `docs/RUNBOOK.md` cross-reference, `docs/index.html` bento card swap (Operator reference replaces stale Ollama-era classifier-source card).
- Tests: 209 → 327 passing (118 added across this minor cycle).

---

## [0.1.0] — 2026-04-23

Initial Evernote → Obsidian migration toolkit. Yarle-based export, basic frontmatter, single-pass rules classifier (`scripts/classify_notes.py`). Foundation for the knowledge-graph work in 0.2.0.
