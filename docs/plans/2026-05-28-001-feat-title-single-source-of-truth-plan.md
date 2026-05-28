---
title: "feat: Title single-source-of-truth (drop frontmatter title + body H1)"
type: feat
status: active
date: 2026-05-28
origin: "Operator confusion — a single note showed its title in 3 places (filename, frontmatter title:, body H1). Wants one source of truth = filename."
---

# feat: Title single-source-of-truth

## Routing Summary

| Runner | Units | Total |
|--------|-------|-------|
| claude | 1, 2, 3 | 3 |

All claude — destructive vault migration (Unit 2 touches ~10k notes) needs judgement on the body-H1 match heuristic, and the granolaSync change (Unit 1) is small but spans a second repo. Operator-confirmed dry-run gate before apply.

---

## Problem Frame

Every Granola-exported note carries its title in THREE places:
1. **Filename** — `2026-05-20 - Sean- Financial Planning.md`
2. **Frontmatter** — `title: "Sean- Financial Planning"`
3. **Body H1** — `# Sean- Financial Planning`

Yarle-imported (Evernote) notes carry it in TWO: filename + frontmatter `title:` (no body H1).

The operator finds this confusing — three things to look at for one logical title. They want the **filename to be the single source of truth**, with Obsidian's "Show inline title" setting (already enabled) rendering it visually.

### Why this is safe to change

Verified before planning:
- **The classifier derives title from the filename** (`title = md_path.stem` at `classify_vault.py:430`), NOT from the frontmatter `title:` field. Removing `title:` does not affect classification.
- **No Dataview queries** anywhere in the vault reference `title` — no dashboards break.
- `fix_evernote_titles.py` touches `title:` but it's a one-shot YAML-repair tool, not in the live classification path.

---

## Units

### Unit 1: granolaSync — stop emitting `title:` frontmatter + body H1
**Execution target: claude**
**Repo: `~/Documents/VSStudio/personal/granolaSync`**

#### Tasks
1. `build_frontmatter()`: remove the `f"title: {json.dumps(title)}"` line. Keep `date`, `granola_id`, `up`, `type`, `org`, `context`, `people`, `attendees`, `updated`.
2. `doc_to_markdown()`: remove the `lines.append(f"# {title}")` + the trailing blank line. Body starts straight into the metadata block.
3. Update `TestBuildFrontmatter`:
   - `test_preserves_existing_title_date_granola_id_up` → rename + rewrite to assert title is ABSENT but date/granola_id/up present
   - Any other test asserting `title:` presence → flip to assert absence
4. Verify full granolaSync suite green. Commit.

### Unit 2: evernote-to-obsidian — `strip_redundant_titles.py` migration
**Execution target: claude**
**Repo: `~/Documents/VSStudio/personal/evernote-to-obsidian`**

#### Tasks (tests first per tdd-first)

New `scripts/classify/strip_redundant_titles.py`:
- `strip_title_frontmatter(text) -> tuple[str, bool]` — remove the `title:` line from the frontmatter block. Returns (new_text, changed).
- `strip_matching_body_h1(text, filename_stem) -> tuple[str, bool]` — remove the FIRST body H1 (`# ...`) ONLY IF its text matches the frontmatter title OR the filename stem (minus date prefix). Conservative: leave non-matching H1s alone (they're real section headings).
- `process_file(path, dry_run) -> dict` — returns `{title_stripped: bool, h1_stripped: bool}`.
- `process_vault(vault, folder, dry_run) -> dict` — walk + skip-list + summary counts.
- CLI: `--vault`, `--folder`, `--dry-run`. Atomic tmp+rename writes. Idempotent.

Tests cover: frontmatter strip, body-H1 strip-when-matching, body-H1 KEEP-when-not-matching (critical — don't delete real headings), Yarle note (no body H1, just frontmatter strip), idempotency, dry-run safety, skip-list.

### Unit 3: Dry-run, operator gate, apply, commit
**Execution target: claude**

1. Dry-run on the whole vault. Report: notes with title stripped, notes with body H1 stripped, total touched.
2. **Operator gate**: show the dry-run numbers + a sample of body-H1 removals. Wait for explicit go before the destructive apply (this modifies ~10k notes).
3. Apply. Verify counts match dry-run.
4. Version bumps + CHANGELOG entries in both repos. Commit.

---

## Out of Scope
- Renaming files to remove the date prefix — date prefix stays (needed for sortability + collision avoidance on recurring meetings).
- Touching `wiki/` (operator-curated, different schema) — skip-list already excludes it.
- The body-H1 strip for notes where the H1 does NOT match the title — those are real section headings, left intact.

## Final Verification
1. granolaSync suite green; evernote-to-obsidian suite green
2. Dry-run count == apply count (no surprises)
3. Re-run dry-run after apply → 0 changes (idempotent)
4. Spot-check 5 notes: no `title:` frontmatter, no duplicate body H1, content intact
5. Version bumps + CHANGELOG both repos
