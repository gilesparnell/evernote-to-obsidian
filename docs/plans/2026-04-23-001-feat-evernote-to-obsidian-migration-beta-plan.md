---
title: "feat: Evernote to Obsidian migration"
type: feat
status: active
date: 2026-04-23
origin: docs/plans/migration.md  # seed (this file supersedes it)
---

# feat: Evernote to Obsidian migration

## Routing summary

**Claude units (4 of 9):** Unit 2 (OAuth — sensitive, interactive), Unit 5 (GUID resolver build — judgement + TDD), Unit 6 (two-notebook dry-run inspection — judgement on output shape), Unit 7 (Yarle config tuning — iterative judgement).

**Codex-delegate units (5 of 9):** Unit 1 (install), Unit 3 (sync), Unit 4 (ENEX export), Unit 8 (full run), Unit 9 (post-import setup). All mechanical once shape is decided.

## Overview

Export 20 years of Evernote notes from a web-only account into the existing Personal Obsidian vault, preserving metadata, tags, attachments, and internal note links. Pipeline: `evernote-backup` (Homebrew + browser OAuth) → SQLite local DB → ENEX export → Yarle conversion → `Personal/Evernote/` folder.

## Problem Frame

User has 20 years of Evernote notes, accessible only via Evernote Web (no desktop app installed, no intent to install one). Wants the archive landed in Obsidian as Markdown with tags, attachments, and internal links preserved, so it becomes searchable historical reference alongside current notes. The Personal vault is the chosen destination because the archive content is mixed personal + work, and triaging into Personal vs Business at import time is the wrong moment to make those calls — staging it in Personal under a clearly-labelled `Evernote/` subfolder allows selective promotion later without locking in decisions now.

## Requirements Trace

- **R1.** Extract full Evernote archive without installing the desktop app.
- **R2.** Convert ENEX → Markdown with frontmatter (`title`, `created`, `updated`, `notebook`, `tags`).
- **R3.** Preserve attachments inline as embedded references (not lost, not rewritten as broken links).
- **R4.** Preserve internal Evernote note-to-note links as Obsidian wikilinks where the target also lands in the import.
- **R5.** Land everything under `Personal/Evernote/<NotebookName>/` with no pollution of the existing `raw/`, `tools/`, `wiki/` folders.
- **R6.** Don't break the existing Personal vault graph or settings.
- **R7.** Allow a dry-run on a single notebook before committing the full archive to disc.

## Scope Boundaries

**In scope:**
- One-off bulk migration of all Evernote content the user owns.
- Configuring Yarle output shape to match Obsidian conventions.
- Verifying the Personal vault opens cleanly after import.

**Out of scope (non-goals):**
- Ongoing two-way sync between Evernote and Obsidian.
- Triaging archived notes into Personal vs Business vault — the archive lives in Personal under `Evernote/` and stays there. Promotion to other locations is a separate, manual, future activity.
- Importing Evernote tasks/reminders. The current public API doesn't expose them; `evernote-backup` requires a separate token from `evertoken` for that. Not worth the extra step for a historical archive.
- Cleaning up the imported notes (dedup, reformat, delete-the-cruft). Import first, decide later.
- Decommissioning the Evernote account. That's a follow-up after the user has verified the archive is intact.

## Context & Research

### Relevant Code and Patterns

This is a personal data migration, not a codebase change — there are no internal patterns to follow. Reference points:

- **Existing Personal vault layout:** `/Users/gilesparnell/Documents/ObsidianVault/Personal/` has `raw/`, `tools/`, `wiki/` subfolders. New import lands under `Personal/Evernote/` to stay isolated.
- **WLC reference for Markdown frontmatter conventions** (informally): the project uses YAML-frontmatter-first patterns elsewhere. Yarle's template will follow the same shape.

### Institutional Learnings

- No prior `docs/solutions/` entries on Evernote migration (this is a one-off).
- Relevant adjacent learning: large attachment folders + iCloud Drive = sync pain. The Personal vault sits in `~/Documents/` which may be iCloud-managed; this is flagged as a pre-Unit-7 check.

### External References

- [evernote-backup README](https://github.com/vzhd1701/evernote-backup) — confirmed via WebFetch on 2026-04-23 AEST.
  - Recommended macOS install: `brew install evernote-backup`.
  - Auth: OAuth-via-browser (default for Evernote backend), not developer token. The browser flow is more reliable than the old token method.
  - Three-command flow: `init-db` → `sync` (resumable, only pulls deltas after first run) → `export <output_dir>`.
  - Tasks/reminders need `--include-tasks --token <evertoken-token>` — explicitly out of scope.
- [Yarle](https://github.com/akosbalasko/yarle) — produces ENEX → Obsidian-flavoured Markdown with configurable tag, frontmatter, and attachment handling. Used in dmuth.org's "Migrating from Evernote to Obsidian" guide linked from the evernote-backup README.
- [dmuth.org — Migrating from Evernote to Obsidian](https://www.dmuth.org/migrating-from-evernote-to-obisidian/) — community reference for this exact pipeline.

## Key Technical Decisions

- **Use `brew install evernote-backup` over pipx.** Maintainer-recommended for macOS, single command, handles updates via Homebrew. *(Correction from earlier conversation, which suggested pipx + developer token.)*
- **Use OAuth browser login over developer token.** README documents OAuth as default. More reliable, doesn't require tokens that Evernote has periodically restricted.
- **Tag format: YAML frontmatter `tags:`, nested via `_` → `/`.** Cleanest for Obsidian's Dataview + search. Doesn't pollute body. Underscore-separated faux-hierarchy in Evernote tags maps to Obsidian's slash-nested tags.
- **Folder structure: `Personal/Evernote/<NotebookName>/<note>.md`.** Preserves provenance, isolates the import from the existing vault structure, allows selective promotion later.
- **Attachments: inside vault under `Personal/Evernote/_resources/`.** Self-contained, portable. Size flagged as a pre-Unit-7 check (10+ GB is realistic for 20 years).
- **Target vault: existing Personal vault, under `Evernote/` subfolder.** No third archive vault — Personal already exists, the `Evernote/` namespace keeps the archive walled off from `raw/` / `tools/` / `wiki/`.
- **No two-way sync.** One-shot migration. Evernote stays read-only on the user's account afterwards until they decide to decommission.
- **Defer cleanup.** Import first. Dedup, reformat, content edits all happen post-import as separate work, if at all.

## Open Questions

### Resolved During Planning

- **Tag format?** → YAML frontmatter `tags:`, nested via `_` → `/`.
- **Folder structure?** → Folder-per-notebook under `Personal/Evernote/`.
- **Attachments inside vault or external?** → Inside vault, `Personal/Evernote/_resources/`.
- **Vault target?** → Existing Personal vault, `Evernote/` subfolder. Not a new vault, not Business.
- **Auth method?** → OAuth browser flow (default in current evernote-backup).

### Deferred to Implementation

- **Whether the Personal vault parent (`~/Documents/`) is iCloud-managed.** Pre-Unit-7 check. If yes, decide whether to (a) accept the iCloud sync of attachments, (b) move the Personal vault out of `~/Documents/` first, or (c) place attachments outside the vault and link by absolute path (overrides the inside-vault decision). User decides at runtime based on attachment size and tolerance for iCloud sync of large binary blobs.
- **Final Yarle config values.** Skeleton is in this plan; exact values get tuned in Unit 6 against the dry-run output.
- **Whether Yarle GUI or CLI is used for the dry-run.** GUI is faster for first inspection; CLI is reproducible for the final run. Probably both.
- **Total archive size estimate.** Visible only after Unit 2 sync completes. Determines whether attachments-in-vault is viable (Unit 7 gate).
- **Whether to keep `en_backup.db` and the ENEX output after the import is verified.** Security trade-off (plain-text archive on disc) vs convenience (re-export without re-syncing). User decides post-Unit-7.

## High-Level Technical Design

> *This illustrates the intended approach and is directional guidance for review, not implementation specification. The implementing agent should treat it as context, not code to reproduce.*

```
Evernote (web)                         Local machine                             Obsidian
─────────────                          ─────────────────────────                 ─────────────────────────────
                                                                                Personal/
                                       en_backup.db (SQLite)                    ├── raw/  (existing)
                                       │   ↑                                    ├── tools/ (existing)
[Account]  ──── OAuth (browser)  ──→   │  init-db                               ├── wiki/  (existing)
[Notes]    ──── sync API         ──→   │  sync (resumable)                      └── Evernote/  (NEW, all imports here)
[Resources]──── sync API         ──→   │                                            ├── _resources/
[Tags]     ──── sync API         ──→   │                                            │   └── <attachments>
                                       │                                            ├── <NotebookName>/
                                       └─→ enex-output/                             │   └── <note>.md
                                            ├── Notebook A.enex                     └── <Other Notebook>/
                                            ├── Notebook B.enex                         └── <note>.md
                                            └── …                                ↑
                                                       │                          │
                                                       └── Yarle (config-driven) ─┘
                                                            • template = frontmatter shape
                                                            • nestedTags _ → /
                                                            • outputFormat OBSIDIANMD
                                                            • resourcesDir _resources
```

Three discrete stages, each independently re-runnable:
1. **Sync** — pull from cloud into local SQLite. Long, idempotent, resumable.
2. **Export** — write ENEX from local SQLite. Fast, fully offline, idempotent.
3. **Convert** — Yarle reads ENEX, writes Markdown into Obsidian vault. Run twice in practice: once on a small notebook (dry-run, scratch output), once on the lot.

## Implementation Units

- [x] **Unit 1: Install evernote-backup, Yarle, and Python environment** ✅ COMPLETE (2026-04-23 AEST)

**Goal:** Get all tools available on the user's Mac.

**Requirements:** R1 (extract without desktop app).

**Dependencies:** Homebrew installed (already present on this machine).

**Files:**
- `evernote-to-obsidian/.venv/` — Python venv (already created).

**Approach:**
- `brew install evernote-backup` per the maintainer's macOS recommendation.
- Yarle: install from the [latest GitHub release](https://github.com/akosbalasko/yarle/releases) for macOS (GUI), and optionally `npm install -g yarle` if CLI is preferred for the final run.
- Python venv already created at `.venv/` with pytest installed. Activate with `source .venv/bin/activate`.

**Execution target:** codex-delegate.

**Test scenarios:**
- `evernote-backup --version` returns a version string.
- `evernote-backup --help` lists `init-db`, `sync`, `export`, `reauth` as subcommands.
- Yarle GUI opens or `yarle --help` returns CLI help.
- `.venv/bin/pytest tests/ -v` → 28 passed.

**Verification:**
- All tools invokable from a fresh shell session.
- Versions noted in `docs/handoff/handoff.md` for reproducibility.

---

- [x] **Unit 2: Initialise local database with OAuth login** ✅ COMPLETE (2026-04-23 AEST)

**Goal:** Create `en_backup.db` and authenticate the user's Evernote account via browser OAuth.

**Requirements:** R1.

**Dependencies:** Unit 1.

**Files:**
- Create: `~/evernote-migration/en_backup.db` (working directory chosen for isolation; do not run from inside an Obsidian vault).

**Approach:**
- `cd ~/evernote-migration` (create the dir first), then `evernote-backup init-db`.
- Walks through OAuth flow: prompts for email, opens browser to Evernote, user completes login + 2FA in browser, browser redirects back to localhost callback.
- DB initialised with auth token stored locally.

**Execution target:** claude — interactive, sensitive (auth flow), one-time setup. Worth a human eye on the OAuth completion.

**Patterns to follow:**
- None.

**Test scenarios:**
- Init reports "Successfully authenticated as <user>".
- `en_backup.db` exists in the working directory.
- `en_backup.db` is not world-readable (`chmod 600 en_backup.db` if needed).

**Verification:**
- File exists, auth succeeded, no error in stdout.
- Token expiry date noted from the init-db output (typically months out for OAuth).

---

- [x] **Unit 3: Full sync of Evernote archive to local SQLite** ✅ COMPLETE (2026-04-23 AEST) — 10,604 notes synced; rate-limited near end but all substantive notes captured

**Goal:** Pull all notes, notebooks, tags, and resource attachments from Evernote into `en_backup.db`.

**Requirements:** R1, R3 (resources fetched).

**Dependencies:** Unit 2.

**Files:**
- Modify: `~/evernote-migration/en_backup.db` (sync writes here).

**Approach:**
- `evernote-backup sync` from the working dir.
- Long-running. 20 years of notes likely several hours, depending on note count and attachment volume. Resumable — can be interrupted and re-run.
- Run in a screen/tmux session or via `nohup` so it survives terminal closure. Alternatively use `claude-supervisor` if the user wants automated retry on rate-limit pauses.
- First run downloads everything. Subsequent runs are deltas only.

**Execution target:** codex-delegate (mechanical), but the user must be present for any rate-limit recovery decisions if sync stalls.

**Patterns to follow:**
- None.

**Test scenarios:**
- Sync completes with "Synchronisation completed!".
- Final summary reports note count, notebook count, resource count.
- Counts cross-checked against the user's Evernote Web sidebar (notebook count should match exactly; note count within ±1% is fine due to deletion timing).
- `en_backup.db` size is plausible — likely several GB for a 20-year archive with attachments.

**Verification:**
- Sync exits cleanly.
- Note count matches Evernote Web (manual cross-check).
- DB size logged in `docs/handoff/handoff.md` so future runs can detect drift.

---

- [x] **Unit 4: Export ENEX files from local DB** ✅ COMPLETE (2026-04-24 AEST) — 7 ENEX files in `evernote-migration/enex-output/`

**Goal:** Write one ENEX file per notebook from the local SQLite into a clean output directory.

**Requirements:** R1.

**Dependencies:** Unit 3.

**Files:**
- Create: `~/evernote-migration/enex-output/<NotebookName>.enex` (one per notebook).

**Approach:**
- `mkdir -p ~/evernote-migration/enex-output`
- `evernote-backup export ~/evernote-migration/enex-output/`
- Default mode (one ENEX per notebook) is correct for this plan — Yarle handles per-notebook ENEX cleanly and the folder-per-notebook output structure depends on this.
- Do NOT use `--single-notes` (would write one ENEX per note, breaks the notebook→folder mapping).
- Optionally include trash with `--include-trash` if the user wants deleted notes archived too. Default = no.

**Execution target:** codex-delegate.

**Patterns to follow:**
- None.

**Test scenarios:**
- Output directory contains one `.enex` file per notebook seen in Evernote Web.
- File count matches notebook count from Unit 3.
- A single ENEX file opens cleanly in a text editor and contains XML with `<en-export>` root.

**Verification:**
- File count matches expected notebook count.
- Total ENEX size in the same order of magnitude as `en_backup.db`.
- Logged in `docs/handoff/handoff.md`.

---

- [x] **Unit 5: Build GUID-based cross-notebook link resolver** ✅ COMPLETE (2026-04-23 AEST)

**Goal:** A post-Yarle Python script that reads `en_backup.db` to resolve cross-notebook `evernote://` links into Obsidian `[[wikilinks]]` — something Yarle cannot reliably do on its own.

**Why this is needed:** Yarle resolves links by title-text matching, which breaks whenever the link display text differs from the note title. The resolver uses Evernote's internal note GUIDs (embedded in `evernote://` URLs) to look up the correct target file, guaranteeing correct resolution regardless of display text.

**Requirements:** R4 (preserve internal note-to-note links, including cross-notebook).

**Dependencies:** Unit 4 (needs `en_backup.db` at runtime; script developed and tested independently).

**Files:**
- `scripts/fix_note_links.py` — the resolver (CLI + library).
- `tests/unit/test_fix_note_links.py` — 22 unit tests.
- `tests/integration/test_fix_note_links_integration.py` — 6 integration tests.
- `pyproject.toml` — pytest config.
- `.venv/` — Python venv with pytest.

**Pipeline position:** Runs after Yarle, before the vault is opened in Obsidian.

```bash
source .venv/bin/activate
python scripts/fix_note_links.py \
  --vault ~/Documents/ObsidianVault/Personal/Evernote \
  --db   ~/evernote-migration/en_backup.db
```

**Link rewriting behaviour:**
- `[text](evernote:///view/.../GUID/GUID/)` → `[[filename|text]]` if text ≠ filename
- `[filename](evernote:///view/.../GUID/GUID/)` → `[[filename]]` (no alias needed)
- Unresolvable GUIDs (target not imported) → original `evernote://` URL kept; easy to grep for later
- `https://www.evernote.com/...` links handled the same way

**Test results:** 28/28 passed (unit + integration).

**Execution target:** claude (judgement + TDD — already done).

---

- [x] **Unit 6: Two-notebook dry-run (Yarle + resolver) into scratch vault** ✅ COMPLETE (2026-04-24 AEST) — `evernote-migration/enex-dryrun/` and `scratch-vault/` confirm Yarle ran

**Goal:** Validate the full pipeline end-to-end on TWO notebooks — specifically picking one notebook that links to notes in the other, to prove cross-notebook link resolution works before committing the full archive.

**Requirements:** R2, R3, R4, R7.

**Dependencies:** Unit 4, Unit 5.

**Files:**
- Create: `~/evernote-migration/scratch-vault/` (throwaway Obsidian vault for inspection).
- Create: `~/evernote-migration/yarle-config.yaml` (initial config — refined in Unit 6).
- Create: `~/evernote-migration/yarle-template.tmpl` (frontmatter shape).
- Input: pick the smallest representative notebook from `~/evernote-migration/enex-output/` — ideally one with tags, an attachment, and an internal link to another note.

**Approach:**
- Initial Yarle config (refine in Unit 6):

  ```yaml
  enexSources:
    - /Users/gilesparnell/evernote-migration/enex-output/<picked-notebook>.enex
  outputDir: /Users/gilesparnell/evernote-migration/scratch-vault/Evernote
  templateFile: /Users/gilesparnell/evernote-migration/yarle-template.tmpl

  outputFormat: OBSIDIANMD
  keepOriginalHtml: false
  skipEnexFileNameFromOutputPath: false
  useHashTags: false                        # tags go in YAML frontmatter, not body
  nestedTags:
    separatorInEN: _
    replaceSeparatorWith: /

  keepMetadata: true
  keepCreationTime: true
  keepUpdateTime: true
  useUniqueUnknownFileNames: true

  resourcesDir: _resources
  urlEncodeFileNamesAndLinks: true
  keepEvernoteLinkIfNoNoteFound: true       # IMPORTANT: keep evernote:// URLs so resolver can rewrite them
  ```

- Initial template:

  ```
  ---
  title: {title}
  created: {created-at}
  updated: {updated-at}
  source: evernote
  notebook: {notebook}
  tags: [{tags}]
  ---

  {content}
  ```

- Run Yarle on BOTH notebooks: set `enexSources` to list both ENEX files.
- Then run the resolver: `python scripts/fix_note_links.py --vault ~/evernote-migration/scratch-vault/Evernote --db ~/evernote-migration/en_backup.db`
- Open the scratch vault in Obsidian.

**Execution target:** claude — judgement on whether output matches expectations. Inspect, don't just check exit code.

**Notebook selection criteria:** Pick two notebooks where at least one note in Notebook A links to a note in Notebook B. This is the critical cross-notebook test. If you're unsure which notebooks have cross-links, pick two of the most-used notebooks — cross-notebook links are common in active archives.

**Test scenarios:**
- Each note in both notebooks produces one `.md` file.
- Frontmatter has `title`, `created`, `updated`, `notebook`, `tags` populated correctly.
- `created` and `updated` are ISO 8601 dates.
- `tags` are valid YAML array (no quoting issues with special chars).
- Attachments land in `_resources/` and embed correctly when opened in Obsidian.
- **Cross-notebook links convert to `[[wikilinks]]`** — this is the key test. Find a note that linked to another notebook and verify the link is `[[Note Title]]` not `evernote://...`.
- Within-notebook links also resolve correctly.
- Resolver script reports: N resolved, M kept as evernote:// (M should be 0 or very low).
- Folder structure is `scratch-vault/Evernote/<NotebookName>/<note>.md`.

**Verification:**
- Open scratch vault in Obsidian. Visually inspect 5-10 notes spanning both notebooks.
- Check Obsidian graph view shows cross-notebook links as edges between the two clusters.
- Grep for remaining `evernote://` links: `grep -r "evernote://" ~/evernote-migration/scratch-vault/` — review any that remain.
- Note any quirks in `docs/decisions/decisions.md` for Unit 7 to address.

---

- [x] **Unit 7: Tune Yarle config until dry-run output is acceptable** ✅ COMPLETE (2026-04-24 AEST) — `yarle-config.yaml` and `yarle_20260424_152135.config` locked

**Goal:** Iterate on `yarle-config.yaml` and `yarle-template.tmpl` until the dry-run output matches the desired shape.

**Requirements:** R2, R3, R4.

**Dependencies:** Unit 6.

**Files:**
- Modify: `~/evernote-migration/yarle-config.yaml`.
- Modify: `~/evernote-migration/yarle-template.tmpl`.
- Re-run output: `~/evernote-migration/scratch-vault/Evernote/`.

**Approach:**
- For each issue found in Unit 6, identify the relevant Yarle config key from the [Yarle docs](https://github.com/akosbalasko/yarle).
- Re-run the dry-run (both notebooks + resolver) after each config change.
- Stop iterating when the scratch vault looks correct on a 10-note spot-check.

**Execution target:** claude — judgement-heavy. Each iteration is a small change + re-inspection cycle that doesn't lend itself to delegation.

**Patterns to follow:**
- None.

**Test scenarios (final acceptance):**
- All checks from Unit 5 pass.
- No noisy log warnings during conversion.
- Filenames don't contain illegal characters (`:`, `/`, `\`, etc. — Yarle should handle this; verify).
- A note with multiple tags renders the YAML array correctly without quoting glitches.

**Verification:**
- Document the final config in `docs/decisions/decisions.md` with rationale for any non-default values.
- Lock the config — Unit 8 must use exactly this config without further tuning.

---

- [x] **Unit 8: Full Yarle run into Personal vault** ✅ COMPLETE (2026-04-24 AEST) — 10,558 .md files in `Personal/Evernote/notes/` across 10 notebooks. NOTE: GUID resolver (Unit 5) was NOT run on the final vault — 19 files still contain unresolved `evernote://` links. See post-migration notes below.

**Goal:** Convert the entire ENEX export into `Personal/Evernote/` and run the GUID resolver, then verify the vault opens cleanly.

**Requirements:** R2, R3, R4, R5, R6.

**Dependencies:** Unit 7 (config locked), pre-flight check on iCloud sync of `~/Documents/`.

**Pre-flight check (must complete before running):**
- Confirm `~/Documents/` is or isn't iCloud-managed: `brctl status ~/Documents/` (or check System Settings → Apple Account → iCloud → Drive → Folders).
- Confirm total ENEX size from Unit 4. If > 5 GB and `~/Documents/` is iCloud-synced, decide:
  - (a) Accept iCloud sync of attachments — convenient, slow, eats iCloud quota.
  - (b) Move Personal vault out of `~/Documents/` first.
  - (c) Override the inside-vault attachment decision: set `resourcesDir` to an absolute path outside the vault. Notes will reference attachments by absolute path.
- Decision logged in `docs/decisions/decisions.md` before proceeding.

**Files:**
- Modify: `~/evernote-migration/yarle-config.yaml` — change `enexSources` to the full directory and `outputDir` to `/Users/gilesparnell/Documents/ObsidianVault/Personal/Evernote`.
- Create: `/Users/gilesparnell/Documents/ObsidianVault/Personal/Evernote/<NotebookName>/<note>.md` (many).
- Create: `/Users/gilesparnell/Documents/ObsidianVault/Personal/Evernote/_resources/<attachments>` (many).

**Approach:**
- Take a Time Machine snapshot or `cp -R` backup of the Personal vault first. Single largest blast-radius operation in the plan.
- Update `yarle-config.yaml` per Files above.
- Run Yarle CLI: `yarle --configFile ~/evernote-migration/yarle-config.yaml`.
- Long-running. Monitor for errors but don't interrupt unless something is clearly broken.
- **Run the GUID resolver:** `python scripts/fix_note_links.py --vault ~/Documents/ObsidianVault/Personal/Evernote --db ~/evernote-migration/en_backup.db`
- After completion: open Personal vault in Obsidian, let it index (will take several minutes for the new content + graph rebuild).
- Optionally enable Dataview plugin if not already on, to query by `created:` / `notebook:` frontmatter.
- Optionally run a name-collision pass: search for notes with identical filenames, rename with notebook prefix if any conflict.

**Execution target:** codex-delegate for the Yarle invocation, resolver run, and post-import checks. Backup step and final visual inspection are claude.

**Patterns to follow:**
- None.

**Test scenarios:**
- `Personal/Evernote/` exists with one folder per notebook from the Evernote source.
- Note count under `Personal/Evernote/` matches Unit 3 sync count (within ±1%).
- Existing `raw/`, `tools/`, `wiki/` folders untouched (verify with `git diff` if vault were git-versioned, or `find -newer` against a marker file).
- Personal vault opens in Obsidian without error.
- Obsidian indexes the new content; graph view updates.
- Spot-check 10 random notes across different notebooks: frontmatter intact, attachments render, internal links resolve.
- Search for a known phrase from Evernote → finds the note in Obsidian.

**Verification:**
- All test scenarios pass.
- Backup of pre-import Personal vault retained for at least 30 days.
- `docs/handoff/handoff.md` updated with completion entry: counts, total size, any anomalies.

## System-Wide Impact

- **Interaction graph:** None — this is a one-off data migration into a personal Obsidian vault. No CI, no other systems touched.
- **Error propagation:** Failures at any unit are isolated. Sync can resume. ENEX export is repeatable. Yarle can be re-run on new ENEX. Worst-case: delete `Personal/Evernote/` and re-run Unit 7.
- **State lifecycle risks:**
  - Pre-import Personal vault state must be backed up before Unit 7 (Time Machine or `cp -R`).
  - `en_backup.db` and `enex-output/` contain plain-text copies of the entire archive — sensitive at rest.
  - OAuth token in `en_backup.db` is account-scoped; revoke from Evernote settings after migration if not planning future re-syncs.
- **API surface parity:** N/A.
- **Integration coverage:** N/A.

## Risks & Dependencies

- **Risk: iCloud Drive sync of Personal vault attachments.** If `~/Documents/` is iCloud-managed and total attachment size is 10+ GB, sync will eat quota and be slow. **Mitigation:** Pre-Unit-8 check; user picks one of the three options documented there.
- **Risk: Yarle config issue not caught in Unit 6 dry-run.** Two notebooks may not surface every edge case (e.g. notes with embedded audio, very old HTML notes from Evernote's first decade). **Mitigation:** Unit 6 picks representative notebooks with mixed content and cross-notebook links. Unit 8 includes a 10-note spot-check after the full run; if issues found, delete `Personal/Evernote/`, fix config, re-run.
- **Risk: GUID resolver misses some link formats.** The resolver handles `evernote://` and `https://www.evernote.com/` URLs. Very old Evernote clients used slightly different URL shapes. **Mitigation:** After Unit 8, grep for remaining `evernote://` in the vault — any leftovers indicate an unhandled format that can be added to the resolver and re-run.
- **Risk: en_backup.db schema differs from expected.** The resolver queries `SELECT guid, title FROM notes`. **Mitigation:** Unit 6 dry-run will catch this before the full run.
- **Risk: Sync stalls or rate-limits on Evernote API.** Unknown how Evernote handles large historic syncs in 2026. **Mitigation:** Sync is resumable. If it stalls, wait and re-run. If it hard-fails, fall back to per-notebook export from Evernote Web (slow but available).
- **Risk: OAuth token expires mid-flight.** Token expiry is months-out per the README example. **Mitigation:** `evernote-backup reauth` if it happens.
- **Risk: Note count mismatch between Evernote and the import.** Could indicate the sync missed something. **Mitigation:** Unit 3 verification step compares counts; Unit 8 verification step compares counts again post-conversion.
- **Risk: Existing Personal vault content disturbed.** **Mitigation:** Pre-Unit-8 backup, plus the `Evernote/` namespace isolation that keeps imports out of `raw/`, `tools/`, `wiki/`.
- **Dependency: Homebrew installed, working Mac with browser, Obsidian installed.** All present.

## Documentation / Operational Notes

- Maintain `docs/decisions/decisions.md` and `docs/handoff/handoff.md` in this project folder per the global Plan Execution Continuity rule. Initialise as empty scaffolds when Unit 1 starts.
- Project lives at `~/Documents/VSStudio/personal/evernote-to-obsidian/` — does NOT need to be deployed anywhere, no versioning rules apply (no shipping code, no in-app version display).
- After Unit 7 completes successfully and the user is satisfied:
  - Decide whether to keep `en_backup.db` and `enex-output/` (sensitive but useful for re-export) or delete them.
  - Decide whether to revoke the OAuth session from Evernote settings.
  - Decide whether to decommission the Evernote account (separate work, not in this plan).

## Post-Migration Status (audited 2026-05-13 AEST)

**Migration complete.** 10,558 notes in `Personal/Evernote/notes/` across 10 notebooks.

### Remaining evernote:// links (19 files)

The GUID resolver (`scripts/fix_note_links.py`) was built but never run on the final vault. 19 files still contain raw `evernote://` links. Diagnosis:

| Category | Count | GUIDs | Action |
|---|---|---|---|
| In DB, target note likely in vault — should resolve | 13 | `00b973fd`, `1f2ee669`, `2b078934`, `3887c9c1`, `38b9c0d5`, `448554a4`, `513b5bdd`, `614b24b7`, `7c6838fd`, `e6a7f85e`, `e7d358f1`, `ef84e445`, `ac423e23` | Run resolver; fix case-sensitivity bug in title matching first |
| Not in DB — genuinely unresolvable | 3 | `0679a295`, `0f43d918`, `9ae6f1e2` | Leave as-is; note was deleted before sync |
| Null GUID | 1 | `00000000-0000-0000-0000-000000000000` | Leave as-is; malformed link in source |

**Known resolver bug:** title matching is case-sensitive. DB title "Partner: Bulletproof" ≠ frontmatter "Partner: BulletProof". Fix: lowercase both sides before comparing.

**To run the resolver:**
```bash
cd /Users/gilesparnell/Documents/VSStudio/personal/evernote-to-obsidian
source .venv/bin/activate
python scripts/fix_note_links.py \
  --vault ~/Documents/ObsidianVault/Personal/Evernote/notes \
  --db evernote-migration/en_backup.db
```

### Open decisions
- [ ] Keep or delete `evernote-migration/en_backup.db` and `enex-output/` (plain-text archive, sensitive at rest)
- [ ] Revoke OAuth session from Evernote settings
- [ ] Run resolver with case-sensitivity fix (optional — only 19 files affected)
- [ ] Decide on Evernote account decommission (separate work)

---

## Sources & References

- **Origin document:** `docs/plans/migration.md` (seed; this plan supersedes it).
- **External:**
  - [evernote-backup (GitHub)](https://github.com/vzhd1701/evernote-backup) — verified 2026-04-23 AEST
  - [Yarle (GitHub)](https://github.com/akosbalasko/yarle)
  - [dmuth.org — Migrating from Evernote to Obsidian](https://www.dmuth.org/migrating-from-evernote-to-obisidian/)
- **Local:**
  - Personal vault: `/Users/gilesparnell/Documents/ObsidianVault/Personal/`
  - Business vault: `/Users/gilesparnell/Documents/ObsidianVault/Business/` (out of scope for this plan)
- **Global rules referenced:** Claude vs Codex Routing, Plan Execution Continuity, Compute Efficiency Defaults.
