# Evernote → Obsidian Migration Plan (seed)

**Status:** seed / pre-plan. Needs `/ce:plan-beta` to expand into a full execution plan.
**Created:** 2026-04-23 AEST
**Runner:** Claude (planning) → Codex (most execution units, per routing summary)

---

## Goal

Export 20 years of Evernote notes (web-only account, no desktop app) into an Obsidian vault with metadata, tags, attachments, and internal note-to-note links preserved.

## Constraints

- Evernote Web has **no export function** — must extract via API.
- Don't want to install the Evernote desktop app.
- Archive is large (20 years) — sync will be long-running, likely overnight.
- Target vault location: **TBD** (resolve at plan time — see open decisions).

## Chosen pipeline

1. **`evernote-backup`** (Python CLI) authenticated with a **developer token** from https://www.evernote.com/api/DeveloperToken.action
   - Syncs full archive to a local SQLite DB (`en_backup.db`).
   - Then exports ENEX files, one per notebook, into a chosen output directory.
2. **`Yarle`** (Node/Electron, GUI + CLI) — converts ENEX to Obsidian-flavoured Markdown.
   - Configurable frontmatter, tag handling (inline vs YAML vs folder), attachment layout, internal link rewriting.
3. **Obsidian vault ingest + post-import hygiene**
   - Dataview plugin for `created:` / `notebook:` frontmatter queries.
   - Dedup pass for name-collision files.
   - First-time graph build (takes minutes on a 20-year archive).

## Why this pipeline (rationale for the record)

- **evernote-backup over desktop-app-export** — user has web-only access and doesn't want to install the desktop app. evernote-backup is purpose-built for this exact case, uses the same public sync API as the desktop client, and produces standard ENEX.
- **Developer token over email+password login** — Evernote's third-party login flow is fragile (CAPTCHAs, session drift, 2FA prompts mid-sync). A developer token sidesteps all of that and is revocable from the same Evernote settings page.
- **Yarle over Obsidian Importer plugin** — Importer is simpler but less configurable. For a 20-year archive, the shape decisions (tag format, folder structure, attachment paths) matter more than convenience. Yarle lets us iterate the config against a test notebook before committing.

## Open decisions (must resolve before Unit 2)

These are judgement calls, all tagged `claude`:

1. **Tag strategy:** YAML frontmatter `tags:` vs inline `#tag` in body vs folder-per-tag. (Default suggestion: YAML frontmatter + nested-tag separator `_` → `/`.)
2. **Folder structure:** flat vs one-folder-per-notebook vs hierarchy derived from nested tags. (Default suggestion: folder-per-notebook under a top-level `Evernote/` folder for provenance.)
3. **Attachments:** inside vault (`_resources/`) vs external folder referenced by path. (Default suggestion: inside vault — simpler, portable, but check total size first.)
4. **Target vault:** new dedicated vault vs folder inside existing vault. (Default suggestion: new dedicated vault until the imported archive is cleaned up, then merge later if desired.)

## Execution units (draft)

Routing summary: **6 of 10 units are `codex-delegate`** (mechanical CLI / install / run). **4 are `claude`** — decisions in Unit 1, token handling in Unit 3, and the dry-run inspection + config tuning in Units 7–8 where judgement on output shape matters.

| # | Unit | Runner | Notes |
|---|---|---|---|
| 1 | Confirm open decisions above (tag format, folder layout, attachment location, vault target) | `claude` | Judgement call, sets shape of everything downstream |
| 2 | Install `pipx` + `evernote-backup` on macOS | `codex-delegate` | Mechanical; `brew install pipx` → `pipx install evernote-backup` |
| 3 | Mint Evernote developer token, run `init-db` | `claude` | Token is sensitive — one-time interactive setup, don't log the token |
| 4 | Run full sync to local SQLite (long, probably overnight) | `codex-delegate` | Background via supervisor or plain `nohup`; monitor for completion |
| 5 | Export ENEX files from local DB | `codex-delegate` | `evernote-backup export ./enex-output/` |
| 6 | Install Yarle (GUI for first pass, CLI for real run) | `codex-delegate` | Mechanical |
| 7 | Dry-run Yarle on ONE small notebook → scratch vault | `claude` | Inspect output, verify decisions from Unit 1 feel right |
| 8 | Tune `yarle-config.yaml` until output matches decisions | `claude` | Iterative judgement; stop when dry-run output is acceptable |
| 9 | Full Yarle run into real vault | `codex-delegate` | Mechanical once config is frozen |
| 10 | Post-import Obsidian setup (Dataview, dedup, graph build) | `codex-delegate` | Mechanical |

## Security notes

- **Developer token = password-equivalent** for API access. Don't paste into shared terminals, screen-shares, or commit to git.
- **Revoke the token** at https://www.evernote.com/api/DeveloperToken.action once the export is complete.
- **`en_backup.db` contains the full note archive in plain SQLite.** Delete or encrypt at rest once ENEX export is done, especially if the archive contains sensitive content.
- **ENEX output directory** should also be treated as sensitive until imported and no longer needed.

## Reference config snippets (to refine at plan time)

### Yarle config skeleton

```yaml
enexSources:
  - /Users/gilesparnell/Documents/evernote-export
outputDir: /Users/gilesparnell/Obsidian/EvernoteArchive
templateFile: ./yarle-template.tmpl

keepOriginalHtml: false
skipEnexFileNameFromOutputPath: false
useHashTags: true
nestedTags:
  separatorInEN: _
  replaceSeparatorWith: /

keepMetadata: true
keepCreationTime: true
keepUpdateTime: true
useUniqueUnknownFileNames: true

outputFormat: OBSIDIANMD
resourcesDir: _resources
urlEncodeFileNamesAndLinks: true
keepEvernoteLinkIfNoNoteFound: false
```

### Yarle template skeleton

```
---
title: {title}
created: {created-at}
updated: {updated-at}
source: evernote
notebook: {notebook}
tags: {tags}
---

{content}
```

## Handoff / pickup instructions

Next session, run:

```
/ce:plan-beta
```

and reference this file. The plan command should:

1. Resolve the four open decisions in the "Open decisions" section (ask user, don't assume).
2. Expand each execution unit into concrete commands with file paths.
3. Add a "Routing summary" block at the top per the Claude vs Codex Routing rule.
4. Add tests / verification steps for each unit (what "done" looks like).
5. Produce the plan as `docs/plans/evernote-to-obsidian-migration.md` (overwriting this seed), with `docs/decisions/decisions.md` + `docs/handoff/handoff.md` initialised as empty scaffolds per the Plan Execution Continuity rule.
