---
date: 2026-05-13
topic: obsidian-knowledge-graph
---

# Obsidian Knowledge Graph — Universal Classification & Hub Pages

## Problem Frame

10,000+ notes spread across Personal and Business Obsidian vaults with unreliable
folder-based classification. The Evernote import preserved folder names (AWS,
T-Systems, TSC, Personal NoteBook, etc.) but folders are not trustworthy — personal
notes ended up in work folders and vice versa. There is no consistent frontmatter,
no way to query "all meetings with Person X", "all T-Systems notes", or "all
technical write-ups" without manual browsing. The goal is a universal frontmatter
schema, an AI classification pipeline that processes historical notes with
human-review for uncertain cases, and Dataview-powered hub pages built once
classification is complete.

### Note inventory (as of 2026-05-13)
| Source | Count | Current location |
|--------|-------|-----------------|
| Evernote/AWS | 6,375 | Personal vault (likely mostly work, but contaminated) |
| Evernote/T-Systems | 1,720 | Personal vault |
| Evernote/TSC | 958 | Personal vault |
| Evernote/Personal NoteBook | 1,414 | Personal vault |
| Evernote/Work - General | 48 | Personal vault |
| Evernote/Cooking | 40 | Personal vault |
| Obsidian/Meetings | 9 | Personal vault |
| Obsidian/Business | 5 | Business vault |
| Other (Job Hunt, wiki, top-level) | ~35 | Personal vault |

---

## Requirements

### Schema

- **R1.** Every note in both vaults gains a standard frontmatter block. Existing
  frontmatter fields are preserved; new fields are added alongside them.

- **R2.** The schema includes these fields:

  ```yaml
  type: meeting | note | technical | reference | person | company | project | recipe | journal | personal
  org: "Amazon" | "T-Systems" | "TSC" | "Parnell Systems" | "Personal" | <other>
  context: work | personal | education
  people: ["First Last", ...]       # anyone mentioned, present, or addressed
  project: "Project Name"           # optional; omit if not applicable
  up: "[[Hub Page Name]]"           # links to the note's parent hub page
  ```

  `tags` is already natively supported by Obsidian and does not need a custom field.

- **R3.** The `up:` field links each note to exactly one hub page, enabling
  Obsidian graph view to show the radial structure centred on hub pages.

### Classification Pipeline

- **R4.** A classification pipeline processes each note and proposes values for
  all R2 fields, using note content as the primary signal and folder path as a
  secondary hint (not authoritative).

- **R5.** The pipeline assigns a confidence score to each classification. Notes
  above the confidence threshold have frontmatter written automatically. Notes
  below the threshold are added to a review queue without having frontmatter
  written.

- **R6.** The review queue is an Obsidian-readable file (e.g. `classification-review.md`
  or CSV) listing: note path, proposed classification, confidence score, and a
  one-line reason for uncertainty. The user resolves each entry manually, then
  re-runs the write step.

- **R7.** The pipeline is re-runnable. Notes already classified (frontmatter
  present and marked as reviewed) are skipped on subsequent runs.

- **R8.** New Granola-exported notes are classified automatically at export time
  using the same schema, using meeting metadata (attendees, calendar event,
  title) as classification signals.

### Vault Migration

- **R9.** Notes classified as `context: work` are candidates for the Business
  vault. Notes classified as `context: personal` or `context: education` are
  candidates for the Personal vault.

- **R10.** Vault migration runs as a separate, explicit step after classification
  is confirmed — it does not happen automatically during classification. The user
  approves migrations in batches.

- **R11.** When a note moves vaults, its `up:` link is updated to point to the
  correct hub page in the destination vault.

### Hub Pages

- **R12.** Hub pages are built with Dataview queries once classification coverage
  reaches a threshold the user considers sufficient (not necessarily 100%).

- **R13.** The following hub pages are in scope (both vaults, mirrored where relevant):

  | Hub page | Query axis | Vault |
  |----------|-----------|-------|
  | Meetings Homepage | `type: meeting` | Both |
  | Companies Hub | `org: <name>` per org | Business |
  | Technical Write-ups | `type: technical` | Business |
  | People Hub | `people` array contains name | Both |
  | Personal Hub | `context: personal` | Personal |

- **R14.** Each per-company page (e.g. `[[Amazon]]`, `[[T-Systems]]`) lists all
  notes with `org: "Amazon"`, grouped by `type`, newest first.

- **R15.** The People Hub index lists all unique names from `people` fields across
  all notes, each linking to a per-person page generated or maintained manually.

---

## Success Criteria

- Running a Dataview query for `org: "Amazon"` returns only work-related Amazon
  notes, not personal notes that were originally stored in the AWS Evernote folder.
- The Meetings Homepage shows only notes with actual content (no `*No notes recorded.*`).
- A new Granola meeting note has complete frontmatter written at export time
  without any manual step.
- The review queue reaches zero after the user works through it — every note has
  confirmed frontmatter.
- Obsidian graph view shows a clear radial pattern centred on hub pages.

---

## Scope Boundaries

- **Out of scope:** Automatic per-person page generation. The People Hub index
  is auto-generated; individual person pages are created manually as needed.
- **Out of scope:** Backfilling note content. Classification enriches metadata
  only; note body text is never modified.
- **Out of scope:** Cross-vault linking (notes in Business vault linking to notes
  in Personal vault). The two vaults remain independent graphs.
- **Out of scope:** Real-time / watch-based classification of existing notes.
  The pipeline is run on demand.

---

## Key Decisions

- **Confidence-gated writes, not full automation:** Fully automated classification
  at 10,000+ notes risks silent misclassification at scale. A review queue ensures
  uncertain notes get human eyes before frontmatter is committed.
- **Classification before hub pages:** Hub pages built on partially-classified
  data would be misleading. Full (or near-full) classification coverage first
  makes the hub pages trustworthy.
- **Folder path as hint, not authority:** Content wins over folder name when
  they conflict, because the Evernote import is known to have cross-contamination.
- **Vault migration is a separate explicit step:** Moving 8,000+ notes between
  vaults is irreversible at scale. Separating it from classification ensures
  the user can verify classifications before notes move.

---

## Dependencies / Assumptions

- **Claude API access** is available for batch classification (granolaSync already
  uses it; same key).
- **Dataview plugin** is installed in both vaults. All hub pages depend on it.
- Both vaults are on the local filesystem at known paths.
- Confidence threshold set at **0.80** based on manual calibration of 80 AWS
  folder notes: 66% auto-classify, 33% review queue. Untitled/Screenshot notes
  (~15% of corpus) require content read to resolve; filename alone is insufficient.

---

## Outstanding Questions

### Resolve Before Planning

*(none — threshold resolved at 0.80 via calibration)*

### Deferred to Planning

- **[R4][Technical]** What is the optimal batch size and prompt structure for
  classifying notes via Claude API? Some notes are very short (1-2 lines);
  others are multi-page documents.
- **[R6][Technical]** What format is most useful for the review queue — Obsidian
  table, CSV, or a separate tool?
- **[R9][Needs research]** What is the safest mechanism for moving files between
  vaults on macOS without breaking Obsidian wikilinks?
- **[R13][Technical]** Should People Hub per-person pages be stub notes with
  Dataview queries embedded, or static pages maintained manually?

---

## Next Steps

→ `/ce:plan` for structured implementation planning
