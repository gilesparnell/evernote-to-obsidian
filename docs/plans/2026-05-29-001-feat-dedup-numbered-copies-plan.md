---
title: "feat: De-duplicate Yarle numbered note copies"
type: feat
status: completed
date: 2026-05-29
---

# feat: De-duplicate Yarle numbered note copies

## Routing Summary

| Runner | Units | Total |
|--------|-------|-------|
| claude | 1 | 1 |

claude — destructive vault operation; the safety rule + trash/manifest handling are judgement calls. (Per `docs/decisions/decisions.md` 2026-05-14, codex-delegate produced no files on disc in this environment.)

## Problem Frame

Triaging the review queue surfaces many near-identical notes whose only difference is a `.1` (or `.N`) before `.md`. Root cause (investigated 2026-05-29): the Evernote→Markdown exporter **Yarle** derives a note's filename from its title; when two Evernote notes share a title it appends `.1`, `.2`, … to avoid clobbering `Title.md`. This is **not** a classifier defect — the classifier never creates or copies files, and there was never a dedup spec, so no test could have caught it. It is a missing feature (no de-duplication step) acting on dirty source data.

Measured on the Personal vault: **3,297** `*.N.md` files — **562 byte-identical** to their base (true duplicates), **2,625** same-title-but-different-content (NOT duplicates), **105** with no base.

## Solution

`scripts/classify/dedup_notes.py` — conservative, dry-run-first. Deletes a numbered copy ONLY when all hold:
1. name matches `<base>.<digits>.md`,
2. the base `<base>.md` exists,
3. the two files are **byte-for-byte identical** (`filecmp.cmp(shallow=False)`).

The base is always kept. Content-differing pairs and base-less numbered files are left for triage. Reuses `classify_vault._iter_md_files` (so wiki/backup/hidden dirs are skipped — never dedupes inside a backup snapshot). Dry-run by default; `--confirm` moves each copy to `~/.Trash/evernote-dedup-<date>/` (recoverable) and logs it via the shared `_append_deletion_manifest`.

Registry: `dedup-dry` + `dedup-run` (daily tier) so it's one-click in the panel.

## Out of Scope (v1)
- Content-identical files with *different* base titles (only numbered-suffix collisions handled).
- Body-only comparison ignoring frontmatter (byte-identical is the safe v1 signal).
- De-duping the 105 base-less numbered files (can't determine canonical).
- Re-configuring Yarle to prevent future collisions (separate follow-up).

## Acceptance Criteria
- [x] Detects exact numbered duplicates; ignores differing/base-less/backup-dir files
- [x] Dry-run by default; `--confirm` moves to Trash + logs manifest; base kept
- [x] Registry entries; full suite green
- [ ] Operator dry-run on the live vault confirms ~562 removable copies before any `--confirm`

## Final Verification
1. `scripts/classify/venv/bin/pytest -q` — full suite green
2. `dedup_notes.py --vault <Personal>` dry-run reports ~562, deletes nothing
3. Version bump + CHANGELOG + handoff updated
