# Post-Chunk Operator Checklist

Run this checklist every time a classifier chunk finishes. Designed to take **45–60 min of active human attention** per chunk on top of the classifier runtime. Ordered by safety — audit first, destructive operations last.

> **The two goals this serves** (per project north-star):
> 1. Categorise vault notes so they're useful for interview-prep retrieval
> 2. Hard-delete the irrelevant / temporary / rubbish so the vault is a curated brain, not an archive
>
> When in doubt between "keep and tag" vs "delete" — lean delete.

---

## Step 1 — Audit the deletion manifest *(~5 min)*

Confirm nothing important was hard-deleted on this run.

```bash
scripts/classify/venv/bin/python scripts/classify/audit_manifest.py \
  --vault ~/Documents/ObsidianVault/Personal
```

Defaults to showing only the latest run's deletions (what you want post-chunk). Pass `--all-runs` to see every deletion ever, or `--limit 20` to cap output when the manifest is large.

**Decision gate:** Skim the body previews. Look for anything that surprises you.

- ✅ Phone numbers, IDs, single-word jots, addresses → expected, leave them gone
- ❓ A note title that sounds career/work-relevant → cross-reference with the backup tarball at `~/Backups/ObsidianVault-pre-classification-2026-05-14.tar.gz` before considering it lost
- ❌ Anything tagged with a person's name in a way that looks like a meeting → potential bug — flag and check the rule

**If you find a surprise:** restore from the backup tarball using the path from the manifest. The manifest is the audit trail; the tarball is the recovery source.

---

## Step 2 — Triage the review queue *(~30–45 min)*

Open the fresh review HTML in your browser:

```bash
open ~/Documents/ObsidianVault/Personal/classification-review.html
```

Make sure the helper-server is running so the action buttons work:

```bash
scripts/classify/venv/bin/python scripts/classify/review_server.py \
  --vault ~/Documents/ObsidianVault/Personal --port 8765
```

(Leaves the page read-only if you skip the server — you can still manually edit frontmatter or delete via Finder.)

**For each card in the queue, pick one:**

| Situation | Action |
|---|---|
| Body is irrelevant / temporary / rubbish | Multi-select tick → "Delete selected" in the floating toolbar |
| Body has clear interview / STAR / career value | Open in Obsidian, manually add frontmatter, save |
| Body is ambiguous but the title pattern repeats across 5+ cards | Note the pattern — that's a candidate for a new title rule (queue for the next plan session) |
| Classifier proposed wrong type with high confidence | Click "Reclassify" in the helper server, pick the right type |

**Stop when you've cleared the page.** Don't perfect-classify every note — the goal is to either categorise (for retrieval) or delete (for clarity). Anything stuck in the middle goes to delete by default.

---

## Step 3 — Browse and prune the `[[Clippings]]` MOC *(~10 min)*

The body-shape rules dump all image-only / URL-only / embed-only notes into `[[Clippings]]`. Most are Evernote import artefacts (Skitch screencaps, ancient bookmarks) — review and bulk-delete what you don't want.

In Obsidian:
1. Open `[[Clippings]]` (the MOC auto-stubs on first reference)
2. Create the file at the vault root with a Dataview query so you can see every clipping in a sortable table — the literal block is:

   ````markdown
   ```dataview
   TABLE file.folder AS Folder, file.size AS Size
   FROM "Evernote/notes/AWS"
   WHERE type = "clipping"
   SORT file.folder ASC
   ```
   ````

   Triple backticks each on their own line — opening line is exactly ` ```dataview ` and closing line is exactly ` ``` `. The Dataview community plugin must be enabled.
3. For each cluster (e.g. all `*.jpg.md` files from the same year): skim 3–5, decide keep-all / delete-all / individual review
4. Bulk-delete via Obsidian's File Explorer (Cmd+Shift+E → multi-select with Shift/Cmd-click → Cmd+Delete) or Finder. Confirm Settings → Files & Links has "Deleted files: Move to system trash" so deletes are recoverable

**Heuristic for keep-vs-delete:**
- Pre-2020 work clippings with no recent reference value → delete
- Anything with a Skitch annotation that captures a decision, design, or whiteboard → keep
- URL-only bookmarks for sites you haven't visited in 2+ years → delete
- PDFs of contracts, invoices, statements → keep (move to `Personal/Reference/` if you want them out of the AWS folder)

---

## Step 4 — Decide on the next chunk *(~2 min)*

Check progress against the AWS corpus:

```bash
scripts/classify/venv/bin/python <<'PY'
import sys; sys.path.insert(0, ".")
from pathlib import Path
from scripts.classify import frontmatter as fm
base = Path.home() / "Documents/ObsidianVault/Personal/Evernote/notes/AWS"
all_md = list(base.rglob("*.md"))
classified = sum(1 for p in all_md if fm.is_classified(p))
print(f"AWS: {classified}/{len(all_md)} classified ({100*classified/len(all_md):.1f}%)")
print(f"Remaining: {len(all_md) - classified} unclassified")
PY
```

**Pick a chunk size based on the latest run's `ac:` rate:**

| Latest `ac:` rate | Recommended `--limit` | Why |
|---|---|---|
| ≥ 85% | 2000 | Rules are doing the heavy lifting; LM rarely fires; chunk runs fast |
| 70–84% | 1000 | Moderate LM dependency; ~3-4 hour runtime |
| < 70% | 500 | Tune rules first before another big chunk — review the new queue for missed title patterns |

Then run the next chunk (binding `runner=human` rule — operator launches, never auto-triggered):

```bash
scripts/classify/venv/bin/python scripts/classify/classify_vault.py \
  --vault ~/Documents/ObsidianVault/Personal \
  --folder "Evernote/notes/AWS" \
  --limit <CHOSEN_LIMIT> --html
```

---

## One-time vault setup — convert audio markdown links to embeds

Run once across the vault (not per chunk). Yarle's Evernote → Markdown export wrote audio attachments as `[name.m4a](./_resources/...)` markdown links, which Obsidian renders as broken hyperlinks (unescaped spaces in the path trip the resolver). Converting them to `![[name.m4a]]` embed wikilinks gives you inline audio players in every note.

```bash
# Preview what would change (no writes)
scripts/classify/venv/bin/python scripts/classify/audio_link_fix.py \
  --vault ~/Documents/ObsidianVault/Personal --dry-run

# Apply for real (atomic per-file, only writes files that actually change)
scripts/classify/venv/bin/python scripts/classify/audio_link_fix.py \
  --vault ~/Documents/ObsidianVault/Personal
```

Idempotent — running twice is safe (re-runs find zero links to convert). Skip-list matches the classifier's (wiki/, Personal-backup-*/, hidden dirs).

---

## When AWS is done

Roughly 4,000 more unclassified Personal-vault notes outside `Evernote/notes/AWS` — TSC, T-Systems, mixed personal folders. Strategy options:

- **Sweep the whole vault**: drop `--folder` flag, run with `--limit 2000` until done. Lets the classifier decide per-note rather than per-folder.
- **Per-folder chunks**: target specific subfolders (`--folder "Evernote/notes/TSC"`) to keep per-chunk scope predictable.

The per-folder approach is recommended — you can audit results in coherent batches that share organisational context.

---

## When in doubt

- **Reference for every CLI flag and progress-bar field**: `docs/operator-reference.html`
- **Procedures for common scenarios**: `docs/RUNBOOK.md`
- **What's in the review queue right now**: `~/Documents/ObsidianVault/Personal/classification-review.html`
- **What got deleted across all runs**: `~/Documents/ObsidianVault/Personal/.classify_deleted_manifest.json`
- **Live progress of a running batch**: `~/Documents/ObsidianVault/Personal/.classify_progress.json`
