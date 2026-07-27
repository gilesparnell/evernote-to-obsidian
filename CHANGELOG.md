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

## [0.15.0] — 2026-07-27

### What's new
- **Home.md is now the front door to each vault.** Both vaults' Home pages carry a nightly-refreshed "Topics & synthesis" section (topic freshness, health score, wiki links, review-queue count), a jump link to the other vault, and a Curated hubs list preserving the hand-built Evernote-era indexes. Your own edits to Home are never touched — the chain only rewrites its marked section.
- **Every `up:` breadcrumb now lands somewhere.** Eight missing hub pages were created where notes pointed at them (including Meetings in the Personal vault, home to all exported meeting notes) — orphaned breadcrumbs dropped from 61 to 0 in Personal and 1,418 to 1 in Business.
- **Topic summaries file under their own heading.** The wiki index now keeps topic lines under "## Topics" instead of appending them loose at the bottom.

### Under the hood
- `scripts/classify/home_dashboard.py` (new): `build_home_section` + sentinel-safe `write_home`, called from `_step_gardener` for every vault; reuses promoted `gardener.topic_freshness`/`review_queue_count`. Links render only when their target file exists in that vault.
- `scripts/classify/wiki_io.py`: `upsert_index_line` gains opt-in `section=` with same-slug stray-bullet migration (idempotent); `synthesize_topic.py` passes `section="## Topics"`.
- `scripts/classify/moc_audit.py` (new): dry-run-by-default audit of missing canonical `UP_MAP` MOC targets with incoming-reference counts + frontmatter lint (self-referential/dangling `up:`); `--apply` creates Inbox-archetype stubs atomically, never overwrites, skips zero-reference MOCs.
- Vault-side (no code): canonical MOC pages re-pointed `up: [[Home]]` (fixed 7 self-references); `Business/Personal.md` fallback hub got the Inbox query; 12 duplicate/stub entry-point files deleted after body-diff verification; T1–T3 implemented by codex-cli from Claude specs, all verified red-first and locally green (687 passed).

## [0.14.0] — 2026-07-27

### What's new
- **Machine-exhaust files in the gardener report are now clickable.** Each stale report listed under "Machine exhaust" links straight to the file — click it in Obsidian and it opens in the browser instead of you hunting it down in Finder.

### Under the hood
- `scripts/classify/gardener.py`: `_exhaust_files` now returns resolved `Path`s (still sorted by filename, so the coverage-table count and health score are unchanged) and `_exhaust_lines` renders `[name](Path.as_uri())`, which percent-encodes spaces and special characters in vault paths. Vaults with no exhaust keep the plain `none` line. Covered by `tests/unit/classify/test_gardener.py::TestGardenerExhaustLinks` (link rendering, `%20` encoding, plain-none guard), written red-first.

## [0.13.0] — 2026-07-21

### What's new
- **Topic pages can refresh themselves overnight and from the panel.** The nightly chain is ready to classify both vaults, refresh changed topic pages, and keep source-note `topics:` backlinks aligned. The control panel also gets a "Refresh topic pages" action for the same classify → collect → synthesise → backlink path when you want the graph updated during the day.
- **The wiki schema now explains the topic tuning fields.** Topic pages document how `exclude:` trims noisy matches and how source-note `topics:` backlinks are owned, so manual entries stay yours while registered topic links stay current.

### Under the hood
- Registered `refresh-topics` in `scripts/classify/script_registry.py` with the venv interpreter and `nightly_chain.py --mode panel --vaults both`; registry validation now locks that runnable shape. Added `scripts/classify/launchd/com.gilesparnell.granola-nightly.plist.new` as the T6 staging plist for launchd rollout without touching `~/Library/LaunchAgents`.
- Bumped the package version in `pyproject.toml` to `0.13.0` and updated `scripts/classify/templates/wiki_SCHEMA.md` with `exclude:` glob semantics plus managed-slug ownership for `topics:` backlinks.

---

## [0.12.0] — 2026-07-10

### What's new
- **Exclude notes from a topic without losing the ones you want.** Sometimes a note genuinely mentions your topic but doesn't belong on the page — like course-material scaffolding cluttering a reflective topic. Until now your only lever was the alias list, which is all-or-nothing. Now a topic can carry an `exclude:` list of filename patterns (e.g. `Circuit Breakers_*` or `Evernote/*`), and the collector skips those notes even when an alias matches them. Add the line to the topic's page, re-run, and the page re-synthesises from the curated set — your own notes in the page are preserved. This is the "see the page, prune it, regenerate" loop: edit `exclude:`, re-run, done.

### Under the hood
- `Topic` gains an `exclude: list[str]` field (defaults empty); `load_topics` parses + type-checks it. `collect_topic` skips a note when `fnmatch` matches any pattern against either the vault-relative POSIX path or the bare filename, evaluated before alias matching. Changing `exclude` changes the matched source set → new `source_set_hash` → synthesis auto-refreshes without `--force`. 5 tests.

---

## [0.11.0] — 2026-07-10

### What's new
- **The rest of the messy `.1`/`.2` notes are sorted, safely.** After the exact-duplicate cleanup, hundreds of numbered notes remained — but they weren't all the same problem. The new tool sorts them into four buckets: **orphans** (the number is a meaningless leftover — no original exists), **near-duplicates** (99%+ identical to the original), **review** (90–99% similar — worth a human glance), and **genuinely different** (real separate notes that just happened to share a title). It then *only* acts on the safe ones: it renames orphans back to a clean title (and fixes any links pointing at them so nothing breaks), and clears the near-duplicates to the Trash. The review and genuinely-different notes are reported but never touched. On the Personal vault this renamed 58 orphans and removed 56 near-duplicates, leaving the ~293 real distinct notes alone. Everything previews first and is recoverable.

### Under the hood
- New `scripts/classify/cleanup_numbered.py`: `classify_numbered` tiers `Title.N.md` by `difflib` body similarity (orphan / near_dup ≥0.99 / review 0.90–0.99 / different <0.90). `rename_orphans` (true orphans only; base-exists notes belong to other tiers) rewrites inbound wikilinks with exact-target matching (`[[Title.1]]`/`[[Title.1|a]]`/`[[Title.1#h]]`/`[[Title.1.md]]` → base, alias/heading preserved), atomic per-file; multi-orphan collisions skip rather than clobber. The dry-run simulates the sequential base-name claims via a `claimed` set, so the previewed rename/collision counts match the confirmed run exactly. `delete_near_dups` reuses the dedup Trash+manifest path. Dry-run default, `--confirm` to act. 7 tests.

---

## [0.10.0] — 2026-07-10

### What's new
- **Topic pages that write themselves.** Point the tool at a topic — say, Julie's finances — by listing a few phrases it goes by (aliases), and it scans your whole vault, finds every note that mentions it (even untitled ones and notes where the phrase is only in the body), and compiles a single page: a summary, a dated timeline, key facts, open questions, and a linked list of every source note it drew from. Every sentence is tagged with which source it came from, so you can trust it and click straight through. If two notes disagree — like a grant number recorded two different ways — it flags the contradiction instead of quietly picking one. Anything the model *guessed* rather than read is fenced off in a separate "Inferences" section, so you always know what the page actually knows versus what it inferred. It runs on your own machine (LM Studio), so nothing leaves your laptop. You can edit your own notes into a protected region of the page and re-running the tool never touches them.
- **The messy `.1` duplicate notes are cleaned up properly now.** The previous cleanup only caught copies that were *byte-for-byte* identical. But most Yarle `.1.md` copies had the same content with slightly different auto-classification tags — so they slipped through. The new **body-only** mode matches on the note's actual content (ignoring the classification frontmatter), keeps the better-classified original, and clears the rest to the Trash (recoverable). This run removed 397 of them from the Personal vault.

### Under the hood
- New synthesis pipeline in `scripts/classify/`: `topics.py` (stub discovery, NFKD slugify, alias-overlap validation), `collect_topic.py` (word-boundary + unicode-fold alias matching, frontmatter-stripped body scan, `source_set_hash` over body only, body-identical dedup preferring the non-numbered base), `synthesis_prompt.py` (gemma-constrained prose-only prompt + `wiki/SCHEMA.md` conventions + page template with `@generated`/`@user` sentinels), `structured_output.py` (3-tier JSON engine ported from kytmanov, OpenAI-SDK-adapted), `wiki_io.py` (sentinel-safe region replace — malformed markers raise, never write), `synthesize_topic.py` (rank/budget → gemma → deterministic post-pass: multi-source `(src: Bn)` verification, out-of-range demotion to Inferences, unknown-wikilink stripping, code-derived confidence, atomic write). Registered `synthesize` in the control panel.
- Live-run fixes (each with a failing-first regression test): dropped `response_format=json_object` (LM Studio 400s — accepts only `json_schema`/`text`); multi-source citation parsing in both the verification regex and sentence splitter (single-source-only was emptying every section); contradiction callout `>`-prefixing; `sys.path` bootstrap on both CLIs for direct control-panel invocation.
- `dedup_notes.py` `--body-only` mode compares `_strip_frontmatter` bodies; `_append_deletion_manifest` now migrates the legacy bare-list manifest to the `{"deleted": [...]}` schema in place.
- Model: `google/gemma-4-e4b` via LM Studio validated as the synthesis baseline (no cloud escalation needed). Run synthesis with `LMSTUDIO_CTX` set to the model's loaded context to reduce source trimming.

---

## [0.9.0] — 2026-05-29

### What's new
- **One button to pull Granola meetings and classify them.** Until now "Sync Granola meetings" only *pulled* new meetings into `Meetings/` — they sat unclassified until you ran the classifier separately. The new **Sync + classify Granola** does both in one click: pull, then classify just the `Meetings/` folder. Because the classifier skips notes it has already done, only the new meetings get processed. If the Granola pull fails (API/auth), it stops there rather than pretending it worked.

### Under the hood
- New `scripts/classify/sync_granola.py`: `sync_and_classify` runs the granolaSync export (`python3 export_granola.py`) then calls `classify_vault(folder="Meetings")`; export non-zero return → `status="export_failed"`, classify skipped. Export runner + classifier are injectable so the orchestration is unit-tested without hitting Granola's API or the real vault. 3 tests in `tests/unit/classify/test_sync_granola.py`.
- Registry: `granola-sync` entry (daily tier) — runs under the venv, passes `--log-notes` so the new meetings show as clickable obsidian:// links in the console. The existing `granola` (pull-only) entry stays for when you just want the pull.

---

## [0.8.0] — 2026-05-29

### What's new
- **Clear out the duplicate "Title.1.md" notes.** The Evernote export tool (Yarle) appended a number to a note's filename whenever two notes shared a title — which is why you kept seeing near-identical notes ending in `.1` while triaging. A new tool finds the copies that are **byte-for-byte identical** to their original and removes them, keeping the original and leaving genuinely-different same-titled notes alone. It previews by default (lists what it would remove, changes nothing); run it again to confirm. Removed copies go to the Trash (recoverable) and are recorded in the deletion manifest. In the control panel: **Find duplicate copies (dry-run)** then **Remove duplicate copies**.

### Under the hood
- New `scripts/classify/dedup_notes.py`: `_base_path_for` maps `Title.<digits>.md` → `Title.md`; `is_exact_duplicate_copy` flags a numbered file only when the base exists and `filecmp.cmp(shallow=False)` is byte-identical; `find_duplicate_copies` walks via `classify_vault._iter_md_files` (so the wiki/backup/hidden skip-list is honoured — never dedupes inside a backup snapshot); `dedup_vault` is dry-run by default, and on `--confirm` moves each copy to `~/.Trash/evernote-dedup-<date>/` and logs it via the shared `_append_deletion_manifest`. Conservative by design: base always kept, content-differing pairs and base-less numbered files left for triage.
- Registry: `dedup-dry` + `dedup-run` entries (daily tier). 9 tests in `tests/unit/classify/test_dedup_notes.py`.
- Measured baseline on a representative vault: of the numbered-copy files, a minority were byte-identical (removable), most were same-title-different-content (kept), and a few had no base file.
- Plan: `docs/plans/2026-05-29-001-feat-dedup-numbered-copies-plan.md`.

---

## [0.7.0] — 2026-05-28

### What's new
- **Start and stop the triage server from the panel.** The review/triage server used to be a launch command you had to copy into a terminal. Now it has **Start**, **Stop**, and **Open** buttons in the panel — start it, click Open to triage in the browser, Stop it when you're done. It runs in the background and doesn't block your classify runs.
- **Click a note to open it in Obsidian.** "Classify vault (apply)" now logs each note as it's processed — `auto`, `review`, or `purged` — and every note path in the console is a clickable link that opens straight in Obsidian. No more hunting through the review file to find the note you want.
- **Much easier to read.** The explanatory text under each tool was too faint against the dark background. Contrast is lifted across the board (now meets WCAG AA), tool descriptions wrap to two readable lines instead of a faint cut-off line, and the description sits clearly under each tool name.

### Under the hood
- `JobManager` gains a server lifecycle (`start_server`/`stop_server`/`server_status`) tracked separately from the one-shot job slot, so a running server never blocks a classify run; `terminate()` then `kill()` after a 5s grace. `review-server` registry entry is now a real `kind: "server"` with interpreter/argv/url; `validate_registry` enforces the server field set. New endpoints `POST /server/start`, `POST /server/stop`, `GET /server/status/<key>` (400 unknown/non-server, 409 already-running/not-running); detail pane shows Start/Stop/Open for server entries.
- `classify_vault.py` gains `--log-notes`: prints `<decision>\t<relpath>[\t-> <type>]` per note via `tqdm.write`; the `classify-run` registry command passes it. `control_panel.linkify_console_output(text, vault)` HTML-escapes the stream and wraps vault `.md` paths in `obsidian://open` anchors (escape-first, so no XSS); `/status` returns `output_html`, the console renders it.
- Readability: secondary greys lifted (`.tool-desc` grey-600 → grey-400 with 2-line clamp, `.detail .use` grey-400 → grey-300, command label/hints/sublabels raised); console links styled green/underlined.
- Tests: 498 → 520 (server lifecycle 6, registry server 2, server endpoints 5, linkify 4, console-links integration 1, `--log-notes` 2, render controls 2).
- Plan: `docs/plans/2026-05-28-003-feat-panel-servers-linkify-readability-plan.md`.

---

## [0.6.0 → 0.6.1] — 2026-05-28

### What's new
- **A control panel for the whole toolkit.** Instead of remembering which script does what and its exact command, open one local page that lists every operator tool grouped by how often you'd reach for it now — daily tools (classify new notes, audit deletions, spot-check, pull Granola) up top, the occasional vault-migration step next, the finished one-time migrations dimmed at the bottom. Click a tool to see what it does, when to run it, and the exact command; hit **Run** and watch its output stream live in the console with a status pill (idle → running → complete/failed + exit code). One job at a time, so two classifier runs can't race on the vault. Launch it with `scripts/classify/venv/bin/python scripts/classify/control_panel.py --port 8770` then open `http://127.0.0.1:8770`.

### Under the hood
- Three new modules, each independently tested. `scripts/classify/script_registry.py` — a declarative allowlist of runnable scripts (`key`, `name`, `use_case`, `tier`, `interpreter`, `cwd`, `argv`); `validate_registry()` runs at import and rejects missing/duplicate keys or nonexistent script paths. The allowlist is the security boundary: `POST /run` takes a registry KEY, never a command string, so there is no path to arbitrary command execution.
- `scripts/classify/control_panel.py` — `JobManager` runs the chosen script via `subprocess.Popen` on a daemon thread, drains stdout+stderr into an in-memory buffer, and tracks `running` → `complete`/`failed` + exit code; one-at-a-time guard rejects a second run while one is active. A stdlib `http.server` bound to **127.0.0.1 only** serves `GET /` (catalogue), `POST /run` (key → job_id), `GET /status/<id>` (poll), `GET /health` (now reports `version`). 127.0.0.1 bind is deliberate — the vault-deleting scripts must never face the network.
- UI matches the SprintTracker reference design (green-500 on grey-950, Geist + Geist Mono, shadcn-style nav rail). `__version__` is read from `pyproject.toml` (single source of truth) and shown in the brand tag + `/health`.
- Tests: 450 → 492 (registry 14, render 9, job-manager 11, live-server integration 8). Full suite green.
- Plan: `docs/plans/2026-05-28-002-feat-local-script-control-panel-plan.md`.
- **0.6.1** — renamed the panel from "Classifier Control" to **"Obsidian Vault Control Panel"**: it runs the whole vault toolkit (classify, Granola export, audit, migrate), not just classification, so the classifier-centric name undersold it. Title + brand heading in `control_panel.py`; added an `obsidian-vault-control-panel.command` double-click launcher (resolves the repo root, polls `/health`, opens the browser, stops the server on close) guarded by 5 invariant tests that lock its port to the panel's `_DEFAULT_PORT`.

---

## [0.5.0] — 2026-05-28

### What's new
- **One title per note, not three.** Notes used to carry their title in three places — the filename, a `title:` frontmatter field, and (for meeting notes) a duplicate `# Title` heading at the top of the body. That was confusing to maintain. Now the filename is the single source of truth; Obsidian's "Show inline title" setting renders it as the visual heading. A one-time migration stripped the redundant `title:` field from 8,798 existing notes and removed 21 duplicate body headings. Genuine section headings were left untouched.

### Under the hood
- New `scripts/classify/strip_redundant_titles.py`: `strip_title_frontmatter` (removes the `title:` line from the frontmatter block only — body `title:` text is safe), `strip_matching_body_h1` (removes a leading `# X` heading ONLY when X matches the filename stem or de-prefixed title — conservative, leaves real section headings alone), `process_file` / `process_vault` with `--vault` / `--folder` / `--dry-run`. Atomic tmp+rename, idempotent, reuses `classify_vault._iter_md_files` skip-list.
- 19 new tests in `tests/unit/classify/test_strip_redundant_titles.py`. Suite 431 → 450.
- Migration applied after taking a fresh backup tarball: the bulk of scanned notes had their redundant `title:` field stripped and a handful of duplicate body H1s removed. Re-run dry-run confirmed 0 remaining (idempotent). Files still matching `^title:` are all body-text mentions, correctly untouched.
- Companion change in granolaSync (commit `3159831`): `build_frontmatter` no longer emits `title:`, `doc_to_markdown` no longer emits the `# {title}` body heading, so future Granola exports are single-source from the start.
- Safe because nothing downstream reads the frontmatter title: the classifier derives title from `md_path.stem`, and no Dataview query references it.
- Plan: `docs/plans/2026-05-28-001-feat-title-single-source-of-truth-plan.md`.

---

## [0.3.0 → 0.4.1] — 2026-05-26 → 2026-05-27

### What's new
- **`audit_manifest.py` CLI** replaces the ad-hoc heredoc Python the post-chunk checklist used to require. Defaults to showing the most recent run's deletions (what you want after every chunk). Pass `--all-runs` for the full history or `--limit N` for a sample. Removes a recurring source of copy-paste pain (multi-line heredoc + indentation errors + shell delimiter quirks).
- **Audio notes now play inline.** A new `audio_link_fix.py` tool converts every `[name.m4a](./_resources/...)` markdown link Yarle exported into `![[name.m4a]]` Obsidian embed wikilinks. After running once, every audio note in the vault renders a real inline player (play/pause/seek). 84 audio links across 58 notes converted on first run. Idempotent — safe to re-run after any new Evernote import.
- **Image-only, link-only, and embed-only notes no longer waste an LM call.** The classifier now recognises them on its own — Evernote Skitch screencaps, bare URLs, audio/PDF embeds. They land in a new `[[Clippings]]` MOC where you can review them in bulk via Obsidian's graph view rather than triaging them one at a time. A large share of a typical import chunk auto-classifies this way.
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
- Known gap: markdown-wrapped tel links (e.g. `[04XX XXX XXX](tel:...)`) strip to ~32 chars and survive to the review queue rather than purging. Documented v2 enhancement: smarter stripping that collapses `[text](url)` to just `text`. For now, manually delete via the helper-server UI.
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
- **Rules cascade catches more notes for free.** Five new title-pattern rules (cloud-service name prefixes, Evernote web-clip "Cursor and …" titles, GoToWebinar viewer captures, "Inbox – email" exports, camera-export numeric filenames). A meaningful cut to the review queue on the next chunk — every match lifts a note from "burns LM time + might land in review queue" to "instant, free, auto-classified".
- **One-shot title quoter for malformed Evernote YAML.** Applied across a large batch of imported notes; the pipeline no longer crashes on raw `title: 1-1: Foo` lines.
- **HTML review outputs** with click-through `obsidian://` links — review queue and post-run samples both open in any browser.
- **Operator-reference page** on the docs site covering every CLI flag and every progress-bar field, plus three decision gates for when to stop and tune.
- **Long batches survive concurrent triage.** Files deleted or renamed mid-run no longer kill the chunk — they're silently skipped and surfaced as `missing:N` in the progress bar.

### Under the hood
- New module `scripts/classify/review_server.py`. stdlib `http.server`, 127.0.0.1-only bind, every client-supplied path resolved against `--vault` root (`InvalidPath` raised on traversal escape). Endpoints: `GET /health`, `GET /`, `POST /delete`, `POST /delete-bulk`, `POST /reclassify`. Trash goes to `~/.Trash/evernote-cleanup-<YYYY-MM-DD>/` with paired `_resources/` folder. New `bulk_trash_notes` helper: best-effort across a list, per-path errors collected without aborting the batch; `ValueError` on empty input bubbles to HTTP 400. 30 tests including live-server integration per endpoint plus a GET / render-assertion.
- `scripts/classify/rules_classifier.py`: 5 new entries appended to `_TITLE_TYPE_RULES` covering cloud-service name prefixes, Cursor web-clipper, GoToWebinar, Inbox email exports, and `\d{8,}\.(jpg|png|heic|gif)` camera-export filenames. Each anchored to start with `(?:\b|_)` boundary to absorb Evernote's underscore-as-colon substitution. 18 new tests in `TestReviewQueueMinedRules`.
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
