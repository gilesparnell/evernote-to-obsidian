---
title: "feat: Body-Shape Classifier Rules + Tiny-Note Purge"
type: feat
status: active
date: 2026-05-26
origin: "Triage analysis of chunk-3 review queue (566 notes) — see handoff 2026-05-15 + this session's clustering pass"
---

# feat: Body-Shape Classifier Rules + Tiny-Note Purge

## Routing Summary

| Runner | Units | Total |
|--------|-------|-------|
| claude | 1, 2, 3, 4 | 4 |

**Why all claude:** Operator override. The 2026-05-14 decisions log records that two Codex round-trips on the previous plan reported done but produced no files on disc; until that failure mode is diagnosed, all units stay on claude regardless of mechanical-vs-judgement split.

---

## Problem Frame

Analysis of the 566-note chunk-3 review queue (the dominant operational debt per the 2026-05-15 handoff) found that **title-pattern rule mining is a dry well for this corpus**. Title patterns are too varied; the long tail is genuinely diverse.

But **body shape is highly predictable**:

| Body shape | Count | % of review queue | Action |
|---|---:|---:|---|
| Body is just a single image embed (`![alt](path)`) | 321 | 56.7% | Classify → `clipping` type → `[[Clippings]]` MOC |
| Body is just a single URL | 7 | 1.2% | Classify → `clipping` type → `[[Clippings]]` MOC |
| Body is just an Evernote audio/PDF embed | 4 | 0.7% | Classify → `clipping` type → `[[Clippings]]` MOC |
| Body < 30 chars after stripping markdown | 75 | 13.3% | **Hard delete** + log path to manifest |
| **Subtotal — pre-empted before LM** | **407** | **71.9%** | |
| Remainder needing genuine triage | 159 | 28.1% | Existing review-queue flow |

Three rules auto-classify into a new `[[Clippings]]` MOC; one rule hard-deletes tiny single-line notes that are not worth keeping (phone numbers, scribbled addresses, ID strings, half-thoughts). At ~4,000 AWS notes still unclassified, that's ~800–1,100 future review-queue entries avoided in chunks 4–7 alone, plus ~100 future tiny-note junk files deleted instead of cluttering the vault.

### Why the existing rules can't catch these

`classify_vault.py` line 344 short-circuits any note with `len(body) < 50` straight to the review queue with `"too short to classify"` — **before** `rules_classifier.classify()` is ever called. Image-only and tiny-body notes therefore never get a chance at the rule cascade.

The fix is threefold:
1. Add body-shape detection to `rules_classifier.classify()` as a high-confidence early return for `clipping`-type notes (Unit 1 + 2)
2. Add a separate body-shape detector that signals "delete this file" for tiny bodies (Unit 1 + 2)
3. Move the `MIN_BODY_LENGTH` gate to fire only after body-shape detection (Unit 3)

---

## Architecture Overview

*Directional — not implementation specification.*

```
┌─────────────────────────────────────────────────────────────────────┐
│  rules_classifier  (extended by Units 1, 2)                         │
│                                                                     │
│  NEW: _classify_by_body_shape(body, folder_hint) -> dict | None     │
│    Returns dict for clipping-shape bodies:                          │
│      1. Body is single image embed       → type=clipping, conf 0.85 │
│      2. Body is single URL only          → type=clipping, conf 0.85 │
│      3. Body is audio/PDF embed only     → type=clipping, conf 0.85 │
│    Returns None when no shape matches.                              │
│                                                                     │
│  NEW: should_purge_by_body_shape(body) -> bool                      │
│    Returns True iff body < 30 chars after stripping markdown.       │
│    No org/type — caller will delete the file outright.              │
│                                                                     │
│  NEW: UP_MAP entry (moc_map.py)                                     │
│    "clipping" → "[[Clippings]]"                                     │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│  classify_vault.py  (modified by Unit 3)                            │
│                                                                     │
│  Per-note flow (replacing the current MIN_BODY_LENGTH short-cct):   │
│                                                                     │
│    1. If should_purge_by_body_shape(body) → delete file,            │
│       append path to .classify_deleted_manifest.json, increment     │
│       purged counter, NEXT NOTE.                                    │
│                                                                     │
│    2. Else: _classify_note_content(title, body, folder_hint)        │
│       (existing rules → LM cascade). The new clipping shape rules   │
│       fire inside rules_classifier and short-circuit the LM.        │
│                                                                     │
│    3. If result["confidence"] >= 0.80 → write frontmatter (existing │
│       flow handles the new "clipping" type via UP_MAP automatically)│
│                                                                     │
│    4. Else if len(body) < MIN_BODY_LENGTH → review queue with       │
│       "too short to classify" (preserves existing behaviour for     │
│       notes that escape BOTH the purge gate and the clipping rules) │
│                                                                     │
│    5. Else → review queue with the LM's reason.                     │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│  Deletion manifest                                                  │
│                                                                     │
│  Path:  <vault>/.classify_deleted_manifest.json                     │
│  Shape: { "deleted": [ {                                            │
│              "path": "Evernote/notes/AWS/Note.13.md",               │
│              "stripped_body_chars": 7,                              │
│              "body_preview": "Bread rolls",                         │
│              "deleted_at_aest": "2026-05-26T14:32:11+10:00",        │
│              "run_id": "<ISO timestamp of run start>"               │
│           }, ... ] }                                                │
│  Behaviour: appended to (never overwritten) — every run's deletions │
│  are auditable. File starts at {"deleted": []} on first write.      │
│  Atomic write via _fm.write_frontmatter's tmp+rename pattern.       │
└─────────────────────────────────────────────────────────────────────┘
```

### Type / MOC decisions

- **Image / URL / attachment embeds → new type `clipping` → new MOC `[[Clippings]]`**
  Adds one entry to `UP_MAP` in `scripts/classify/moc_map.py`. Obsidian auto-creates the stub `Clippings.md` MOC page on first wikilink resolution; the operator can build it out post-pilot. No `_resources/` to move; the embedded asset files stay where Evernote put them.

- **Tiny bodies → hard delete, no classification**
  The 75 tiny-body notes are not worth a MOC, a `[[Personal]]` tag, or operator attention. Examples from analysis: `Note.13.md` body = `"Bread rolls"`, `Note.16.md` body = phone number, `Note.38.md` body = tel link. These are import artefacts of Evernote's quick-capture flow and represent operator intent that has expired. Hard-deletion is the right call.
  - Manifest captures path + first 50 chars of body so any "wait that one was important" event is reconstructible
  - Manifest is committed alongside the code changes so the deleted-list lives in git history
  - Pipeline does NOT prompt — the operator opted into hard-delete at plan time. The chunk-4 run will silently purge any tiny bodies it encounters.

### Org inference for clipping-shape notes

When `_classify_by_body_shape` matches, the body itself has no content keywords — so org must come from the folder hint:
- Folder hint matches `ORG_KEYWORDS` (e.g. "AWS" → Amazon) → use that org with conf 0.85
- No folder match → org = `"Personal"` (existing fallback in `classify()`)

This mirrors the existing folder-hint logic in `classify()` lines 334–345.

---

## Source Analysis

See this session's research output — clustering of all 566 review-queue records by content shape (script + output not committed; runs against `~/Documents/ObsidianVault/Personal/classification-review.html`). Headline numbers in the Problem Frame table above. Sample remainder list (160 notes) shows: 23 `.N.md` duplicate-suffix files, ~30 short 1-1 notes that the title rule can't reach because the body-length gate fires first (Unit 3 also fixes this), ~25 personal-life notes, ~80 genuinely ambiguous mixed-content notes.

---

## Units

### Unit 1: Design + failing tests for body-shape rules and tiny-note purge
**Execution target: claude**
**Reason:** Type-name choices, regex strictness, and the new delete behaviour are judgement calls. The failing test list IS the spec for Unit 2. tdd-first skill applies — tests must exist and fail before any implementation lands.

#### Tasks

**1a. Tests in `tests/unit/classify/test_rules_classifier.py`** — add a new class:

```python
class TestBodyShapeClippingRules:
    # Rule A: body is a single image embed → clipping
    def test_body_single_image_skitch_classifies_as_clipping()
    def test_body_single_image_other_alt_text_classifies_as_clipping()
    def test_body_image_with_trailing_whitespace_classifies_as_clipping()
    def test_body_image_with_additional_text_falls_through()

    # Rule B: body is a single URL → clipping
    def test_body_single_url_classifies_as_clipping()
    def test_body_url_in_angle_brackets_classifies_as_clipping()
    def test_body_url_with_paragraph_text_falls_through()

    # Rule C: body is an audio or PDF embed → clipping
    def test_body_evernote_audio_embed_classifies_as_clipping()
    def test_body_pdf_image_embed_classifies_as_clipping()

    # Org inference from folder hint
    def test_clipping_uses_folder_hint_for_amazon_org()
    def test_clipping_no_folder_hint_defaults_to_personal()

    # Confidence
    def test_clipping_confidence_above_auto_threshold()  # >= 0.80

    # Integration — clipping wins over normal cascade for matching shapes
    def test_clipping_image_wins_over_title_keyword()


class TestShouldPurgeByBodyShape:
    # True cases
    def test_purges_tiny_phone_number_body()
    def test_purges_tiny_address_fragment()
    def test_purges_body_with_only_whitespace_and_markdown_chars()
    def test_purges_29_char_body()  # boundary

    # True case — empty bodies also purge per operator decision (2026-05-26)
    def test_purges_empty_body()  # 0 chars after strip
    def test_purges_whitespace_only_body()

    # False cases
    def test_does_not_purge_30_char_body()  # boundary
    def test_does_not_purge_image_only_body()  # clipping rule wins at pipeline level
```

**1b. Tests in `tests/unit/classify/test_moc_map.py`** — add:

```python
def test_clipping_type_maps_to_clippings_moc():
    assert up_for_type("clipping") == "[[Clippings]]"
```

**1c. Tests in `tests/unit/classify/test_classify_vault_helpers.py`** — add a new class:

```python
class TestTinyBodyDeletion:
    # Pipeline-level: a tiny file gets removed + manifest entry written
    def test_tiny_body_file_is_deleted_from_disk(tmp_path)
    def test_tiny_body_deletion_appends_to_manifest(tmp_path)
    def test_tiny_body_deletion_does_not_review_queue(tmp_path)
    def test_tiny_body_purged_counter_increments(tmp_path)
    def test_clipping_shape_short_body_is_not_deleted(tmp_path)
    # ^ Critical: a 20-char body that's a single image must clip, not purge

    # Manifest format
    def test_manifest_starts_with_empty_deleted_list_on_first_write(tmp_path)
    def test_manifest_atomic_write(tmp_path)  # tmp + rename
    def test_manifest_entry_contains_required_fields(tmp_path)
```

**1d. Tests for pipeline-flow ordering** in `test_classify_vault_helpers.py`:

```python
class TestBodyShapeOrdering:
    # Purge gate runs FIRST — image-only short body must clip, not purge
    def test_image_only_body_classifies_as_clipping_not_deleted(tmp_path)
    # Short body with no shape match AND no keyword match still review-queues
    def test_short_unmatched_body_still_review_queues_too_short(tmp_path)
    # Short 1-1 note now reaches the title-rule cascade (side-effect fix)
    def test_short_one_on_one_body_classifies_as_meeting(tmp_path)
```

**Verification gate for Unit 1:**

```bash
scripts/classify/venv/bin/pytest tests/unit/classify -v 2>&1 | tail -40
```

Expected: every new test fails with `AttributeError`, `NameError`, or assertion failure (not `ImportError` / `SyntaxError`). Existing 286+ tests still pass.

---

### Unit 2: Implement the rules + purge detector
**Execution target: claude**
**Reason:** Operator override pending Codex diagnosis. Spec is tight from Unit 1's tests; mostly mechanical but stays on claude.

#### Tasks

**2a. `scripts/classify/moc_map.py`:**
```python
UP_MAP: dict[str, str] = {
    ...,
    "clipping": "[[Clippings]]",  # body-shape classifier — single image/url/embed bodies
}
```

**2b. `scripts/classify/rules_classifier.py`:**

```python
# Module-level constants
_BODY_IMAGE_ONLY_RE = re.compile(r"^\s*!\[[^\]]*\]\([^)]+\)\s*$")
_BODY_URL_ONLY_RE = re.compile(r"^\s*<?(https?://\S+?)>?\s*$")
_BODY_AUDIO_EMBED_RE = re.compile(
    r"^\s*\[Evernote\s+\d{8,}[^\]]*\.(?:m4a|mp3|wav)\]\([^)]+\)\s*$",
    re.IGNORECASE,
)
_BODY_PDF_EMBED_RE = re.compile(
    r"^\s*!\[[^\]]*\.pdf[^\]]*\]\([^)]+\)\s*$",
    re.IGNORECASE,
)
_BODY_STRIP_MARKDOWN_RE = re.compile(r"[*_#>\[\]()\\\n\t]")
_TINY_BODY_MAX_CHARS = 30
_BODY_SHAPE_CONFIDENCE = 0.85


def should_purge_by_body_shape(body: str) -> bool:
    """True iff the body is < 30 chars after markdown wrappers are stripped.
    Includes the zero-length case (empty / whitespace-only files) per
    operator decision (2026-05-26). Caller deletes the file; no MOC, no
    review queue."""
    stripped = _BODY_STRIP_MARKDOWN_RE.sub("", body).strip()
    return len(stripped) < _TINY_BODY_MAX_CHARS


def _classify_by_body_shape(body: str, folder_hint: str) -> dict | None:
    """Return a full classify() result dict for clipping-shape bodies, or
    None when no shape matches. Org comes from folder hint."""
    # ... checks the four clipping regexes; if any match, derives org from
    # folder hint via the same logic as classify() (lines 334-345), and
    # returns: {"type": "clipping", "org": ..., "context": ...,
    #           "people": [], "tags": [], "confidence": 0.85, "reason": ...}
```

**2c. Wire `_classify_by_body_shape` into `classify()` as the first check** after `folder_lower` is computed and before org/type keyword scoring. If it returns a dict, early-return.

Do **NOT** wire `should_purge_by_body_shape` into `classify()` — that's a pipeline-level decision, handled in Unit 3.

**2d. Reason strings:**
- `"body-shape: single image (clipping)"`
- `"body-shape: single URL (clipping)"`
- `"body-shape: Evernote audio embed (clipping)"`
- `"body-shape: PDF embed (clipping)"`

**Verification gate for Unit 2:**

```bash
scripts/classify/venv/bin/pytest tests/unit/classify/test_rules_classifier.py tests/unit/classify/test_moc_map.py -v
```

Expected: every clipping test in `TestBodyShapeClippingRules` and `test_clipping_type_maps_to_clippings_moc` now passes. `TestShouldPurgeByBodyShape` tests pass. Pipeline tests (`TestTinyBodyDeletion`, `TestBodyShapeOrdering`) still fail — that's Unit 3.

---

### Unit 3: Pipeline wiring — purge gate + clipping flow + manifest
**Execution target: claude**

#### Tasks

**3a. New helper in `scripts/classify/classify_vault.py`:**

```python
_MANIFEST_FILENAME = ".classify_deleted_manifest.json"
_DELETED_BODY_PREVIEW_CHARS = 50

def _append_deletion_manifest(vault: Path, run_id: str, md_path: Path,
                               body: str) -> None:
    """Atomically append a deletion record to the manifest. Creates the
    manifest with an empty deleted list on first write."""
    # Read existing manifest (or {"deleted": []}), append entry, write atomically
    # via tmp + rename per the project's iCloud-safe write pattern.
```

**3b. Modify the per-note loop:**

Remove the existing `if len(body) < MIN_BODY_LENGTH:` block at line 344–351. Replace with:

```python
if rules_classifier.should_purge_by_body_shape(body):
    if not dry_run:
        _append_deletion_manifest(vault, run_id, md_path, body)
        md_path.unlink()
        time.sleep(ICLOUD_SLEEP_SECONDS)
    purged += 1
    continue

result, lm_latency = _classify_note_content(title, body, folder_hint)
if lm_latency is not None:
    lm_latencies.append(lm_latency)

if result["confidence"] >= CONFIDENCE_THRESHOLD:
    # ... existing auto-classify branch
elif len(body) < MIN_BODY_LENGTH:
    review_queue.append({
        "path": md_path,
        "proposed_type": "?",
        "proposed_org": "?",
        "confidence": 0.0,
        "reason": "too short to classify",
    })
else:
    # ... existing review-queue branch
```

**3c. New counter `purged` threaded through:**
- Local in `classify_vault()`
- `set_postfix_str` segment: `"purged:N"`
- `.classify_progress.json` heartbeat: `totals.purged`
- Summary dict + CLI summary print

**3d. `run_id`** = `started_at` ISO string (already exists), passed into `_append_deletion_manifest` so all of one run's deletions share a run_id.

**3e. `--dry-run` behaviour:** do NOT delete files, do NOT write the manifest, do increment `purged` counter. The CLI summary should report `"would purge: N (dry run)"`.

**Verification gate for Unit 3:**

```bash
scripts/classify/venv/bin/pytest tests/unit/classify -v
scripts/classify/venv/bin/pytest -q  # full suite
```

Expected: all `TestTinyBodyDeletion` + `TestBodyShapeOrdering` tests pass. Full suite green (286+12+8+3 = ~309 tests).

**Manual smoke (operator runs, no commit):**

```bash
# 1. Dry-run on a small slice — confirm purged counter advances, no files deleted
scripts/classify/venv/bin/python scripts/classify/classify_vault.py \
  --vault ~/Documents/ObsidianVault/Personal \
  --folder "Evernote/notes/AWS" \
  --limit 20 --dry-run --html

# 2. Inspect the printed summary; expect purged:N segment
# 3. Confirm no .classify_deleted_manifest.json was written (dry-run)
# 4. Confirm no files actually disappeared
ls ~/Documents/ObsidianVault/Personal/Evernote/notes/AWS | wc -l
```

---

### Unit 4: Re-run on the AWS folder, verify the lift, write handoff
**Execution target: claude**

#### Tasks

**4a. Pre-flight safety checks (operator confirms before proceeding):**
- Backup tarball `~/Backups/ObsidianVault-pre-classification-2026-05-14.tar.gz` still exists (`ls -la` confirms)
- Existing `classification-review.html` archived to `classification-review-2026-05-26-pre-bodyshape.html`
- Current commit on `main` is clean and pushed

**4b. Run the classifier:**

```bash
scripts/classify/venv/bin/python scripts/classify/classify_vault.py \
  --vault ~/Documents/ObsidianVault/Personal \
  --folder "Evernote/notes/AWS" \
  --limit 700 --html
```

The 566 review-queue notes are unclassified (no frontmatter), so they'll be picked up. Already-classified 2,124 notes are skipped via `is_classified()`. Limit 700 covers the queue plus margin.

**4c. Verification (judgement-heavy — Claude does this part):**

1. **Manifest check** — open `~/Documents/ObsidianVault/Personal/.classify_deleted_manifest.json`. Expected ~75 entries from this run (matches the tiny-body cluster size from analysis). Scan for any path that looks important to the operator before they consider the deletion final.

2. **Clipping count** — query the vault for `type: clipping` count via `sample_classified.py --filter type=clipping --n 50`. Expected ~330 (321 image + 7 URL + 4 audio/PDF; some may have stripped to other shapes).

3. **New review-queue size** — open the new `classification-review.html`. Expected ≤ 200 (target ~160). > 200 means a body-shape rule is misfiring; investigate before moving on.

4. **False-positive spot check** — sample 10 newly-`clipping`-classified notes via `sample_classified.py --filter type=clipping --n 10` and confirm each one's body really is just an embed.

5. **Short 1-1 sanity check** — confirm at least one short `1-1_ *.md` note from the previous review queue now auto-classified as `meeting` (the side-effect fix from Unit 3).

**4d. Documentation:**

1. Write a handoff entry at the top of `docs/handoff/handoff.md`:
   - Date (Australia/Sydney AEST)
   - Runner tag: `human` (next runner is operator)
   - What landed: 3 clipping rules + 1 purge rule + manifest infrastructure
   - Before/after numbers (review-queue size, auto-rate, purge count)
   - What remains in the ~160-note review queue
   - Next action: triage the remainder via the helper-server UI, then chunk 4

2. Append a decisions log entry at the top of `docs/decisions/decisions.md`:
   - Date (AEST)
   - Title: "New `clipping` type + `[[Clippings]]` MOC for Evernote import artefacts"
   - Why we chose a new MOC over re-using `[[Reference]]` (operator preference for separation)
   - Why tiny-body notes hard-delete instead of review-queue (operator opted in, manifest provides audit trail)

3. Update `CHANGELOG.md` — bump `pyproject.toml` 0.2.0 → 0.3.0 (minor: new behaviour, no breaking changes). Entry structure per the global Versioning Discipline rule:

```markdown
## [0.3.0] — 2026-05-26

### What's new
- The classifier now recognises image-only, link-only, and embed-only notes
  on its own — no more sending Evernote screenshots to the LM for review.
- One-line notes (phone numbers, scribbled addresses) are now automatically
  removed from the vault. A manifest of every deleted file is kept under
  `.classify_deleted_manifest.json` if you want to see what went.

### Under the hood
- `rules_classifier`: new `_classify_by_body_shape` + `should_purge_by_body_shape`
  helpers. New `clipping` R2 type, mapped to `[[Clippings]]` MOC.
- `classify_vault`: MIN_BODY_LENGTH gate moved after rule cascade; new purge
  branch with atomic manifest append.
- ~75 tiny notes purged + ~330 notes auto-classified as `clipping` on the
  chunk-3 review-queue re-run (vs the prior 566-note review queue).
```

**4e. Operator gate (binding `runner=human` rule):**

Draft the chunk-4 command in the handoff entry. **Do NOT auto-launch.**

```bash
# Chunk 4 — operator runs manually after reviewing handoff
scripts/classify/venv/bin/python scripts/classify/classify_vault.py \
  --vault ~/Documents/ObsidianVault/Personal \
  --folder "Evernote/notes/AWS" \
  --limit 2000 --html
```

---

## Out of Scope

These came up in analysis but are explicitly NOT in this plan:

- **Bulk-delete tooling for the auto-classified clipping notes.** After Unit 4, the operator may want to delete all 300+ Skitch clippings. The new helper-server already supports bulk-delete from the review HTML; a "bulk operations on auto-classified notes by type/org" tool is a future plan.
- **Finer-grained MOCs** (`image-clipping` vs `url-clipping`). Decision: one `[[Clippings]]` MOC for now; split later if the operator finds it useful.
- **Re-running already-classified AWS notes** to see if body-shape rules would have changed any classifications. They wouldn't (existing classifications cleared the 0.80 gate via the LM); not worth the disruption.
- **Recovery tooling for the deletion manifest.** The manifest is for audit, not restoration. If the operator wants to un-delete, they have the 2026-05-14 backup tarball.
- **Rule-ordering investigation for short 1-1 notes.** Unit 3 fixes this *as a side effect* — short 1-1 notes will now reach the title-rule cascade and match the existing `1-1` rule. Confirmed in Unit 4 spot-checks.

---

## Final Verification (after all units)

1. `scripts/classify/venv/bin/pytest -q` — full suite green
2. `scripts/classify/venv/bin/pytest -m integration_live` — passes against running LM Studio (no behavioural change expected; confirms we didn't break the LM cascade)
3. Re-run AWS chunk completes with review-queue size ≤ 200, purge count matches manifest size
4. `.classify_deleted_manifest.json` present in vault root, JSON valid, all entries have the required fields
5. `git log --oneline` shows logical commits — Unit 1 (failing tests), Unit 2 (implementation), Unit 3 (pipeline wiring + manifest), Unit 4 (handoff + decisions + CHANGELOG + version bump)
6. `pyproject.toml` version 0.2.0 → 0.3.0
7. `CHANGELOG.md` entry added with "What's new" + "Under the hood" sections per the global template
8. `docs/handoff/handoff.md` top entry covers this plan's outcome
