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

## [0.5.0] — 2026-05-28

### What's new
- **One title per note, not three.** Notes used to carry their title in three places — the filename, a `title:` frontmatter field, and (for meeting notes) a duplicate `# Title` heading at the top of the body. That was confusing to maintain. Now the filename is the single source of truth; Obsidian's "Show inline title" setting renders it as the visual heading. A one-time migration stripped the redundant `title:` field from 8,798 existing notes and removed 21 duplicate body headings. Genuine section headings were left untouched.

### Under the hood
- New `scripts/classify/strip_redundant_titles.py`: `strip_title_frontmatter` (removes the `title:` line from the frontmatter block only — body `title:` text is safe), `strip_matching_body_h1` (removes a leading `# X` heading ONLY when X matches the filename stem or de-prefixed title — conservative, leaves real section headings alone), `process_file` / `process_vault` with `--vault` / `--folder` / `--dry-run`. Atomic tmp+rename, idempotent, reuses `classify_vault._iter_md_files` skip-list.
- 19 new tests in `tests/unit/classify/test_strip_redundant_titles.py`. Suite 431 → 450.
- Migration applied to the live vault 2026-05-28 after a fresh backup (`~/Backups/ObsidianVault-pre-title-strip-2026-05-28.tar.gz`): 9,771 scanned, 8,798 titles stripped, 21 body H1s stripped. Re-run dry-run confirmed 0 remaining (idempotent). The 956 files still matching `^title:` are all body-text mentions, correctly untouched.
- Companion change in granolaSync (commit `3159831`): `build_frontmatter` no longer emits `title:`, `doc_to_markdown` no longer emits the `# {title}` body heading, so future Granola exports are single-source from the start.
- Safe because nothing downstream reads the frontmatter title: the classifier derives title from `md_path.stem`, and no Dataview query references it.
- Plan: `docs/plans/2026-05-28-001-feat-title-single-source-of-truth-plan.md`.

---

## [0.3.0 → 0.4.1] — 2026-05-26 → 2026-05-27

### What's new
- **`audit_manifest.py` CLI** replaces the ad-hoc heredoc Python the post-chunk checklist used to require. Defaults to showing the most recent run's deletions (what you want after every chunk). Pass `--all-runs` for the full history or `--limit N` for a sample. Removes a recurring source of copy-paste pain (multi-line heredoc + indentation errors + shell delimiter quirks).
- **Audio notes now play inline.** A new `audio_link_fix.py` tool converts every `[name.m4a](./_resources/...)` markdown link Yarle exported into `![[name.m4a]]` Obsidian embed wikilinks. After running once, every audio note in the vault renders a real inline player (play/pause/seek). 84 audio links across 58 notes converted on first run. Idempotent — safe to re-run after any new Evernote import.
- **Image-only, link-only, and embed-only notes no longer waste an LM call.** The classifier now recognises them on its own — Evernote Skitch screencaps, bare URLs, audio/PDF embeds. They land in a new `[[Clippings]]` MOC where you can review them in bulk via Obsidian's graph view rather than triaging them one at a time. Expected ~330 chunk-3 notes (of 566) auto-classified this way on the next AWS run.
- **Tiny notes are now hard-deleted from the vault, not review-queued.** Bodies with under 30 chars of semantic content (phone numbers, one-line scribbles, leftover Evernote stubs) are removed on the spot. The vault becomes a curated brain instead of an archive of every scrap ever captured. Every deletion is recorded in `.classify_deleted_manifest.json` at the vault root with path, body preview, and timestamp — if a deletion ever surprises you, the manifest is the audit trail.
- **Short 1-1 notes now classify automatically instead of being review-queued.** Previously the < 50 char body gate ran before the rules cascade, so a 30-char `1-1_ Dragon.md` body never got a chance to match the existing 1-1 title rule. Now it does.
- **Dry-run is fully safe.** `--dry-run` counts what would be purged but doesn't touch the filesystem or write the manifest. CLI summary shows "purged=N (dry-run, no files removed)" so you can see what's coming before committing.
- **Progress bar shows the new `purged:N` segment** alongside `auto` / `review` / `skip` / `missing`, plus `purged` now appears in `.classify_progress.json` totals so external watchers can track it without parsing the log.

### Under the hood
- `scripts/classify/rules_classifier.py`: new `_classify_by_body_shape(body, folder_hint)` short-circuits `classify()` with `type="clipping"` (conf 0.85) for bodies matching `_BODY_IMAGE_ONLY_RE`, `_BODY_URL_ONLY_RE`, `_BODY_AUDIO_EMBED_RE`, or `_BODY_PDF_EMBED_RE`. New public `should_purge_by_body_shape(body)` returns True when stripped body < 30 chars (including the zero-length case per operator decision 2026-05-26). Org inference mirrors the existing folder-hint fallback.
- `scripts/classify/moc_map.py`: one entry added — `"clipping": "[[Clippings]]"`.
- `scripts/classify/classify_vault.py`: per-note loop restructured. New order: (1) rules cascade, (2) purge gate iff rules < 0.80 confidence, (3) LM fallback iff body survived the purge gate, (4) auto-classify or review-queue based on best-of-two confidence. The previous `if len(body) < MIN_BODY_LENGTH` short-circuit was removed; the "too short to classify" review-queue label is preserved for 30-49 char bodies that escape both the clipping rules and the purge gate. New `_append_deletion_manifest(vault, run_id, md_path, body)` writes atomic tmp+rename JSON. New `_update_postfix` helper de-duplicates the progress-bar string between the purge branch and the classify branch.
- `_write_heartbeat` signature gained a `purged` keyword; `.classify_progress.json` `totals` dict now includes `purged`.
- Tests: 353 → 387 passing. New classes: `TestBodyShapeClippingRules` (13 tests), `TestShouldPurgeByBodyShape` (8 tests), `TestBodyShapeReason` (2 tests), `TestTinyBodyDeletion` (9 tests), `TestBodyShapeOrdering` (3 tests), plus one `TestUpMap` MOC test. Six pre-existing tests updated where their tiny convenience bodies (testing checkpoint writes, directory skipping, review-queue rendering — not tininess itself) would have triggered the new purge gate.
- Plan: `docs/plans/2026-05-26-001-feat-body-shape-classifier-rules-plan.md`.
- Known gap: markdown-wrapped tel links (`[041 581 7988](tel:041%20581%207988)`) strip to 32 chars and survive to the review queue rather than purging. Documented v2 enhancement: smarter stripping that collapses `[text](url)` to just `text`. For now, manually delete via the helper-server UI.
- `scripts/classify/audio_link_fix.py`: new CLI with `--vault`, `--folder`, `--dry-run` flags. Module-level `_AUDIO_LINK_RE` with negative-lookbehind `(?<!!)` so existing `![[name]]` embeds and `![alt](path)` image embeds are never re-wrapped (idempotent by construction). Per-file atomic tmp+rename writes mirror the iCloud-safe pattern in `frontmatter.write_frontmatter`. Files with zero audio links are not touched at all — preserves mtime and avoids iCloud sync churn. Reuses `classify_vault._iter_md_files` so the skip-list (wiki/, Personal-backup-*/, hidden dirs) matches the classifier's.
- Tests: 387 → 412 passing. New `TestConvertAudioLinks` (13 tests for the regex transform), `TestProcessFile` (5 tests for atomic single-file write + idempotency + zero-link no-op), `TestProcessVault` (7 tests for skip-list + folder scope + summary counts). One pre-existing flaky test (`test_short_body_goes_to_review_with_too_short_reason`) fixed by adding the LM-mock that the rest of `TestClassifyVault` uses — was state-dependent on LM Studio's response.
- `scripts/classify/audit_manifest.py`: new CLI with `load_manifest`, `latest_run_id`, `entries_for_run`, `format_entry`, `audit` functions. Defaults `--last-run-only` (overridable via `--all-runs`). 19 new tests in `tests/unit/classify/test_audit_manifest.py` covering missing manifest, corrupt JSON, multi-run filtering, formatting, and the limit cap.
- Tests: 412 → 431 passing.

---

## [0.2.0 → 0.2.3] — 2026-05-15

### What's new
- **Review server starts in under a second.** Earlier versions took multiple seconds to start because the import chain dragged in the LM SDK (openai → httpx → ~30 transitive modules) just to look up a wikilink. The server now imports only what it needs.
- **Triage page auto-prunes already-actioned rows on refresh.** Cards for notes you've already deleted or reclassified disappear from the page on the next refresh — no more visual clutter, no more 404s when you click an already-trashed row. The header shows "N pending · M already actioned (hidden)" so you can see how much you've gotten through.
- **Multi-select bulk delete in the triage UI.** Each card now has a checkbox; tick several, then click "Delete selected" in the floating toolbar to trash them in one batch. "Select all" / "Clear selection" controls at the top of the page. Partial failures (a file that's already been moved by another action, or a path edge case) surface in an alert without rolling back the batch — what could be deleted, is.
- **In-browser triage with one-click delete + reclassify.** New helper server reads the review queue and serves it back with action buttons on every card — no more leaving the page to fix a misclassification. Deletes go to macOS Trash (recoverable via Finder), not `rm`. Both actions append to per-vault audit logs.
- **Rules cascade catches more AWS notes for free.** Five new title-pattern rules (AWS service prefixes, Evernote web-clip "Cursor and …" titles, GoToWebinar viewer captures, "Inbox – email" exports, camera-export numeric filenames). Expected ~32% cut to the chunk-3-shape review queue on the next chunk — every match lifts a note from "burns 8 s of LM time + might land in review queue" to "instant, free, auto-classified".
- **One-shot title quoter for malformed Evernote YAML.** Applied across 1,540 AWS notes; the pipeline no longer crashes on raw `title: 1-1: Foo` lines.
- **HTML review outputs** with click-through `obsidian://` links — review queue and post-run samples both open in any browser.
- **Operator-reference page** on the docs site covering every CLI flag and every progress-bar field, plus three decision gates for when to stop and tune.
- **Long batches survive concurrent triage.** Files deleted or renamed mid-run no longer kill the chunk — they're silently skipped and surfaced as `missing:N` in the progress bar.

### Under the hood
- New module `scripts/classify/review_server.py`. stdlib `http.server`, 127.0.0.1-only bind, every client-supplied path resolved against `--vault` root (`InvalidPath` raised on traversal escape). Endpoints: `GET /health`, `GET /`, `POST /delete`, `POST /delete-bulk`, `POST /reclassify`. Trash goes to `~/.Trash/evernote-cleanup-<YYYY-MM-DD>/` with paired `_resources/` folder. New `bulk_trash_notes` helper: best-effort across a list, per-path errors collected without aborting the batch; `ValueError` on empty input bubbles to HTTP 400. 30 tests including live-server integration per endpoint plus a GET / render-assertion.
- `scripts/classify/rules_classifier.py`: 5 new entries appended to `_TITLE_TYPE_RULES` covering AWS service prefixes, Cursor web-clipper, GoToWebinar, Inbox email exports, and `\d{8,}\.(jpg|png|heic|gif)` camera-export filenames. Each anchored to start with `(?:\b|_)` boundary to absorb Evernote's underscore-as-colon substitution. 18 new tests in `TestReviewQueueMinedRules`.
- `scripts/classify/classify_vault.py`: pre-scan (`_count_already_classified`) and main loop body both wrap file IO in `try/except FileNotFoundError → skip`. New `skipped_missing` counter threaded through tqdm postfix (`missing:N` segment), `.classify_progress.json` heartbeat (`totals.skipped_missing`), summary dict, and CLI summary print.
- `scripts/classify/lm_classifier.py`: `openai.OpenAI()` cached via `@functools.lru_cache(maxsize=1)` — fixes the FD leak that crashed runs at ~297 LM calls. Side effect: LM avg dropped 18.7 s → 8.4 s from connection-pool reuse.
- `scripts/classify/frontmatter.py`: `_split()` catches `yaml.YAMLError` so unquoted titles don't crash the pipeline. Same defence flows through `read_frontmatter` / `is_classified` / `write_frontmatter`.
- `scripts/classify/html_renderer.py`: adds `render_review_queue_html_with_actions` and `parse_review_queue_md` for the review server's GET /. Self-contained dark theme. Per-card action buttons (single Delete / Reclassify / Quick-reclassify) plus a multi-select layer: `.select-checkbox` on every card, a floating `.selection-toolbar` that appears once anything is ticked, and a vanilla-JS `doDeleteSelected` handler that POSTs to `/delete-bulk` and fades the moved cards in place. "Select all" / "Clear selection" controls at the top of the queue. `parse_review_queue_md` now takes a `skip_acted_on=False` kwarg; the renderer passes `True` so rows whose file is gone or already has full R2 frontmatter are pruned on each refresh (rendered count + a "M already actioned (hidden)" note in the header).
- New CLIs: `scripts/classify/fix_evernote_titles.py`, `scripts/classify/sample_classified.py` (with `--html`), `scripts/classify/review_server.py`.
- Docs: `docs/operator-reference.html` (single-page reference for every CLI flag and progress-bar field), `docs/RUNBOOK.md` cross-reference, `docs/index.html` bento card swap (Operator reference replaces stale Ollama-era classifier-source card).
- New module `scripts/classify/moc_map.py` (pure data + lookup fn). UP_MAP / up_for_type extracted out of `classify_vault.py` so consumers that don't need the full classifier (e.g. `review_server`) can import them without transitively loading `lm_classifier` → `openai` → `httpx`. `classify_vault.py` re-exports for back-compat. Subprocess regression test asserts `openai` / `httpx` are not in `sys.modules` after `import scripts.classify.review_server`.
- Tests: 209 → 351 passing (142 added across this cycle: rules-mining +18, helper server +20, race tolerance +3, bulk delete +10, queue auto-prune +5, moc_map extraction +9).

---

## [0.1.0] — 2026-04-23

Initial Evernote → Obsidian migration toolkit. Yarle-based export, basic frontmatter, single-pass rules classifier (`scripts/classify_notes.py`). Foundation for the knowledge-graph work in 0.2.0.
