---
title: "feat: Pre-pilot Classification Improvements"
type: feat
status: active
date: 2026-05-14
origin: docs/brainstorms/2026-05-14-pre-pilot-classification-improvements-requirements.md
---

# feat: Pre-pilot Classification Improvements

## Routing Summary

| Runner | Units | Total |
|--------|-------|-------|
| codex-delegate | 1, 2, 3, 4, 5 | 5 |
| claude | 6, 7 | 2 |

**claude units:**
- **Unit 6 (RUNBOOK)** — Semantic documentation work; troubleshooting decisions, tone, and structural calls are judgement-heavy. Two-pass (structure pre-pilot, real examples post-pilot).
- **Unit 7 (status page extension)** — Visual / semantic HTML; weaves into the existing Deep Ocean Tech design and requires content judgement, not mechanical edits.

**Session note (2026-05-14):** During the parent plan, two Codex round-trips reported "done" but produced no files on disc. The codex-delegate tags here reflect *ideal* routing; the operator may continue overriding to Claude until the Codex failure mode is diagnosed. See `docs/decisions/decisions.md` — "Units 4–8 executed by Claude despite codex-delegate tags".

---

## Problem Frame

The 9-unit knowledge-graph classifier plan is code-complete (237 tests passing) and committed across both repos. A pre-pilot review surfaced seven gaps between "code works" and "operator can run this confidently on real data". This plan implements the smallest set of improvements that makes the pipeline pleasant to run, easy to trust, and resilient under the 15-hour AWS scale-out — *without* over-engineering the forward-looking concerns the pilot hasn't yet justified.

The Job Hunt pilot (~35 notes) is the next operational step. Units 1–5 ship *before* the pilot. Unit 6's RUNBOOK lands in two passes (structure before pilot, real examples after). Unit 7 follows Unit 6.

## Source Document

Requirements doc: `docs/brainstorms/2026-05-14-pre-pilot-classification-improvements-requirements.md`

Key decisions carried forward (see origin):
- Pilot runs with plain Markdown review queue — tooling decision deferred to post-pilot
- Hardcoded skip-list over `--safe-mode` flag — defaults must be safe
- Heartbeat JSON over richer telemetry / notifications — overkill for an overnight personal task
- Single comprehensive RUNBOOK over scattered docs — operator wants one grep target
- Defer: review-queue tooling, correction tracking, per-company MOCs, tag governance, `--reclassify` flag, cross-repo sync check

Outstanding technical questions from origin are resolved inline in the unit specs below.

---

## Architecture Overview

*Directional — not implementation specification. Implementer treats this as context, not code to reproduce.*

```
┌────────────────────────────────────────────────────────────────────┐
│  classify_vault.py  (existing — extended by Units 1, 2, 3)         │
│                                                                    │
│  Unit 1 — _iter_md_files()                                         │
│    + skip-list: wiki/, Personal-backup-*/, .obsidian/, .trash/    │
│      Unconditional. No CLI override flag.                          │
│                                                                    │
│  Unit 2 — main loop                                                │
│    + tqdm progress bar wrapping the iterator                       │
│    + running counts (auto/review/lm-avg) via set_postfix_str       │
│                                                                    │
│  Unit 3 — every checkpoint_interval notes + on completion          │
│    + write atomic .classify_progress.json to vault root            │
│    + flat-dict snapshot; ISO-8601 timestamps; complete: true at end│
└────────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────────┐
│  sample_classified.py  (Unit 4 — new CLI)                          │
│                                                                    │
│  --vault <path> [--folder <subfolder>] [--n N=10]                  │
│  [--filter <field>=<value> ...]  [--seed N]                        │
│                                                                    │
│  Walks vault → skip-list filter → is_classified() → --filter       │
│  predicates → uniform-random pick of N → terminal report           │
└────────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────────┐
│  --help enrichment  (Unit 5)                                       │
│  Every CLI under scripts/classify/ gets:                           │
│  - one-line summary in description=                                │
│  - "Common patterns" with 2–3 copy-paste examples in epilog=       │
│  - concrete per-flag help= text                                    │
│  - RawDescriptionHelpFormatter so multi-line formatting survives   │
└────────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────────┐
│  docs/RUNBOOK.md  (Unit 6 — new)                                   │
│  Prerequisites → Procedures (pilot/sample/AWS/migrate) →           │
│  Expected output (3 real examples) → Troubleshooting (flat list,   │
│  symptom/cause/remedy per entry) → Reference                       │
└────────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────────┐
│  docs/status-2026-05-14.html  (Unit 7 — extend)                    │
│  New "How to use it" section: 3-card mini-grid linking RUNBOOK     │
│  with the 3 most common commands. Reuses existing CSS.             │
└────────────────────────────────────────────────────────────────────┘
```

---

## Codebase Context

| Existing artefact | What it has | What this plan extends |
|---|---|---|
| `scripts/classify/classify_vault.py` | `_iter_md_files`, `classify_vault()` main loop, checkpoint logic, review-queue formatting | Units 1, 2, 3 (skip-list, progress bar, heartbeat JSON) |
| `scripts/classify/requirements.txt` | `openai>=1.30`, `PyYAML>=6.0`, `pytest>=8.0` | Add `tqdm>=4.66` (Unit 2) |
| `scripts/classify/__init__.py`, `lm_classifier.py`, `rules_classifier.py`, `frontmatter.py`, `migrate_legacy_up.py`, `migrate_vault.py` | Minimal argparse `--help` | Unit 5 enriches each |
| `tests/integration/classify/test_classify_vault.py` | 13 tests covering pipeline behaviour | Units 1, 2, 3 extend |
| `docs/index.html`, `docs/status-2026-05-14.html` | Hub + status snapshot, Deep Ocean Tech design | Unit 7 extends status page |
| — | — | `docs/RUNBOOK.md` (Unit 6 — new) |
| — | — | `scripts/classify/sample_classified.py` (Unit 4 — new) |
| — | — | `tests/unit/classify/test_sample_classified.py` (Unit 4 — new) |
| — | — | `tests/unit/classify/test_help_output.py` (Unit 5 — new) |

Existing convention reminders (carried from `CLAUDE.md`):
- Test runner: `scripts/classify/venv/bin/pytest` — bare `pytest` can't see PyYAML.
- Atomic writes via `.tmp` + rename on iCloud-synced vault paths.
- Australia/Sydney timezone for any user-facing timestamps; ISO-8601 with offset for machine-readable.

---

## Implementation Units

---

### Unit 1: Scope-Safety Skip-List

**Execution target: codex-delegate**
**Goal:** Make `classify_vault.py` UNCONDITIONALLY skip `wiki/`, `Personal-backup-*/`, `.obsidian/`, `.trash/` even when run vault-wide without `--folder`. Protects hand-curated content (the wiki notes with `type: concept` schema) from accidental overwrite.

**Dependencies:** None. Smallest, foundational. Ship first.

**Files:**
- `scripts/classify/classify_vault.py` — modify `_iter_md_files()`
- `tests/integration/classify/test_classify_vault.py` — extend with skip-list tests

**Approach:**
- Module-level `_SKIP_DIR_PATTERNS: tuple[str, ...] = ("wiki", "Personal-backup")` (literal-or-prefix match against the first path component under the vault). Existing dotfile skip (`.obsidian`, `.trash`) stays as-is.
- In `_iter_md_files`, after the existing dotfile check, test the first component of `path.relative_to(vault).parts` against the skip patterns. `Personal-backup` uses startswith; the others use equality.
- NO CLI flag to override. By design — defaults must be safe.

**Patterns to follow:** Existing `_iter_md_files` skip-loop in the same file.

**Test scenarios (extend `test_classify_vault.py`):**
- Note at `<vault>/wiki/concepts/x.md` is NOT processed when `folder=None` (vault-wide).
- Note at `<vault>/Personal-backup-20260424/note.md` is NOT processed (matches `Personal-backup` prefix).
- Note at `<vault>/Evernote/notes/AWS/note.md` IS processed (sanity — skip-list doesn't over-block).
- A file literally named `wiki.md` at vault root IS processed (skip matches directories, not filename substrings).

**Verification gate:** `scripts/classify/venv/bin/pytest tests/integration/classify/test_classify_vault.py -v` — all tests green, including four new scenarios. Full suite should be 163 + 4 = 167 passing.

---

### Unit 2: Live Progress Bar via tqdm

**Execution target: codex-delegate**
**Goal:** Render a live progress bar in the terminal during classify_vault runs: current/total, percent, ETA, plus a postfix showing `auto:N | review:M | lm-avg:Xs`. Live sense of run health at a glance with no extra tooling.

**Dependencies:** Unit 1 (skip-list affects the total count).

**Files:**
- `scripts/classify/classify_vault.py` — wrap iteration in tqdm; track LM-call latencies
- `scripts/classify/requirements.txt` — add `tqdm>=4.66`
- `tests/integration/classify/test_classify_vault.py` — extend with smoke test

**Approach (decision answered from origin §Outstanding Questions):**
- **tqdm vs hand-rolled:** tqdm. Standard library well-tested, supports `set_postfix_str()`, terminal-aware. 30 LOC of hand-rolled is fragile re-invention. Adding a single ~80 KB dep is worth it.
- Pre-count: walk `_iter_md_files()` once via `list()` to get total; use that as tqdm `total=`. (Cheap — file globbing in Python; we already walk the list to apply skips. Worth the second pass for the ETA.) When `--limit` is set, `total = min(total, limit)`.
- Add `import tqdm` at module top; alias `from tqdm import tqdm`.
- Wrap the iteration: `for md_path in tqdm(file_list, desc="Classifying", unit="note", file=sys.stdout):`.
- Maintain `lm_latencies: list[float]` — append in `_classify_note_content` around the lm_classifier call site using `time.perf_counter()`.
- After each note, build a postfix string: `auto:{n} | review:{m}` and append `| lm-avg:{mean:.1f}s` only when at least one LM call has fired. `pbar.set_postfix_str(...)`.

**Patterns to follow:** None in this repo; tqdm docs at https://tqdm.github.io/.

**Test scenarios:**
- Run `classify_vault(tmp_path, ...)` against a small fixture — assert returned summary dict is unchanged; capture stdout via `capsys` and assert it contains `"Classifying"` (smoke).
- `--limit=0` edge case: tqdm shouldn't crash on empty iter.
- All-already-classified fixture: zero notes processed; tqdm renders empty bar; no crash.

**Verification gate:** `scripts/classify/venv/bin/pytest -q` — full suite green (~168 tests). Plus a manual run against a populated fixture; bar must render with the postfix updating live.

---

### Unit 3: Heartbeat `.classify_progress.json`

**Execution target: codex-delegate**
**Goal:** Every `checkpoint_interval` notes (and once at end-of-run with `complete: true`), atomically write a JSON snapshot to `<vault>/.classify_progress.json`. Operator can `cat` it from any session for non-blocking monitoring during overnight runs.

**Dependencies:** Units 1, 2. Reuses Unit 2's counters and lm_latencies.

**Files:**
- `scripts/classify/classify_vault.py` — add `_write_heartbeat()` helper; call from main loop
- `tests/integration/classify/test_classify_vault.py` — extend with heartbeat tests
- `.gitignore` — add `.classify_progress.json` (vault-scoped, but defensive)

**Approach (decisions answered from origin §Outstanding Questions):**

JSON shape — flat dict, no nested per-folder, no recent-paths list:

```json
{
  "started_at": "2026-05-14T13:42:01+10:00",
  "last_updated": "2026-05-14T17:15:22+10:00",
  "complete": false,
  "vault": "/Users/.../Personal",
  "folder": "Evernote/notes/AWS",
  "totals": {
    "scanned": 2150,
    "auto_classified": 1421,
    "needs_review": 612,
    "skipped_already_classified": 117,
    "lm_calls": 612,
    "lm_call_avg_seconds": 24.7
  }
}
```

- Helper `_write_heartbeat(vault: Path, state: dict, complete: bool)` builds dict, writes to `<vault>/.classify_progress.json.tmp`, renames atomically.
- Called every `checkpoint_interval` notes alongside the existing checkpoint write, AND once unconditionally at end-of-run with `complete=True`.
- Timestamps in ISO-8601 with `+10:00` AEST offset (or `+11:00` AEDT outside DST — use `datetime.now(timezone(timedelta(hours=10)))` for now; treat DST switching as a deferred concern). Wrap once in `_now_aest()` for swappability.

**Patterns to follow:** Existing `frontmatter.write_frontmatter` for the atomic-write pattern.

**Test scenarios:**
- Run pipeline against a fixture with >100 short notes (`checkpoint_interval=50`); assert `.classify_progress.json` exists, parses, ends with `complete: true`.
- Mid-run snapshot: after 60 notes, assert `complete: false` and `totals.scanned == 60`.
- Atomic: assert no `.classify_progress.json.tmp` lingering post-write.
- JSON structure: assert top-level keys + nested `totals` shape match the spec.

**Verification gate:** `scripts/classify/venv/bin/pytest -q` — full suite green. Plus manual: run a real `classify_vault` against a 50+ note fixture; in a separate terminal, `cat .classify_progress.json` mid-run and confirm sane values.

---

### Unit 4: `sample_classified.py` CLI

**Execution target: codex-delegate**
**Goal:** A small CLI that samples N random auto-classified notes from a vault and prints a terminal report with title, key R2 fields, and a body excerpt. Used after each classification run for spot-checking before deciding to proceed.

**Dependencies:** Units 1–3 (reuses skip-list logic from Unit 1; logically sequenced after the pipeline updates so the verification flow is: classify → sample → decide).

**Files:**
- `scripts/classify/sample_classified.py` — new
- `tests/unit/classify/test_sample_classified.py` — new

**Approach (decisions answered from origin §Outstanding Questions):**

CLI: `python scripts/classify/sample_classified.py --vault <path> [--folder <subfolder>] [--n N=10] [--filter <field>=<value> ...] [--seed N]`

- `--n` default 10. If matched set has fewer than N, print all matched and a one-line "only K available" notice.
- `--filter` repeatable; semantics = AND across all filters. OR/NOT deferred to v2 (documented in `--help`).
- `--seed` for reproducible sampling during debugging.
- Reuses `_iter_md_files` skip-list from Unit 1 (extract to a small shared helper or import — implementer chooses cleanest path).
- Uses `frontmatter.is_classified()` and `frontmatter.read_frontmatter()` from Unit 2 (parent plan).

Terminal report per sampled note (ANSI dim grey for separators/labels, default for values; fallback to plain text when stdout isn't a TTY):

```
─────────────────────────────────────────
[1/10]  Evernote/notes/AWS/<filename>.md
        type: meeting | org: Amazon | context: work | conf: 0.94
        up: [[Meetings]]  |  people: ["Alice Smith"]
        tags: ["aws-lp/dive-deep"]
        ━━━ first 200 chars of body ━━━
        Meeting about S3 cross-region replication. Key topics:
        bandwidth costs, failover scenarios, and the new...
```

**Patterns to follow:** Existing `classify_vault.py` argparse setup; `frontmatter.py` API.

**Test scenarios:**
- Fixture: 20 classified notes; `sample(n=5)` returns exactly 5.
- Insufficient: `sample(n=100)` against 20 returns 20 + warning. No crash.
- `--filter type=meeting` returns only meeting-typed notes.
- `--filter org=Amazon --filter type=meeting` AND-combines.
- `--seed 42` returns deterministic sample across runs.
- Unclassified notes are excluded.
- Skip-list applied — wiki/ notes never appear in samples.

**Verification gate:** `scripts/classify/venv/bin/pytest tests/unit/classify/test_sample_classified.py -v` — 7+ tests pass. Plus: after Job Hunt pilot runs, manual eyeball of `sample_classified.py --folder "Job Hunt" --n 10` output.

---

### Unit 5: `--help` Enrichment Across Classifier CLIs

**Execution target: codex-delegate**
**Goal:** Every CLI under `scripts/classify/` becomes self-explanatory via rich `--help` output. Lets RUNBOOK reference `--help` rather than duplicate flag docs.

**Dependencies:** Units 1–4 (so new flags and behaviours land in the help text).

**Files:**
- `scripts/classify/classify_vault.py` — argparse upgrade
- `scripts/classify/migrate_legacy_up.py` — argparse upgrade
- `scripts/classify/migrate_vault.py` — argparse upgrade
- `scripts/classify/sample_classified.py` — already lands rich (Unit 4)
- `tests/unit/classify/test_help_output.py` — new tiny smoke test

**Approach:**

Per CLI:
- `description=` — one-paragraph summary (what it does + when to use it)
- `epilog=` — "Common patterns" with 2–3 copy-paste examples
- Per-flag `help=` — single sentence, concrete, mentions defaults explicitly
- Use `argparse.RawDescriptionHelpFormatter` so multi-line description/epilogue renders correctly

Example pattern (classify_vault):

```
description = """\
Classify Obsidian notes into R2 schema (type/org/context/people/tags) via
a rules-first → LM-Studio-fallback cascade. Writes frontmatter to
high-confidence matches; appends low-confidence to classification-review.md.
"""

epilog = """\
Common patterns:

  # Pilot — Job Hunt folder
  %(prog)s --vault ~/Documents/ObsidianVault/Personal --folder "Job Hunt"

  # AWS scale-out, chunked for visible progress
  %(prog)s --vault ~/Documents/ObsidianVault/Personal \\
    --folder "Evernote/notes/AWS" --limit 500

  # Dry run — see what would happen, no writes
  %(prog)s --vault ~/Documents/ObsidianVault/Personal \\
    --folder "Job Hunt" --dry-run
"""
```

**Patterns to follow:** Python stdlib argparse with `RawDescriptionHelpFormatter`.

**Test scenarios (`test_help_output.py`):**
- For each of the 4 CLIs: `subprocess.run([..., "--help"], capture_output=True)` exits 0, stdout contains the literal string `"Common patterns"`.

**Verification gate:** `scripts/classify/venv/bin/pytest tests/unit/classify/test_help_output.py -v` — 4 smoke tests pass. Plus manual: read each CLI's `--help` and confirm it reads cleanly to fresh eyes.

---

### Unit 6: `docs/RUNBOOK.md`

**Execution target: claude**
**Goal:** A single operator manual that takes the user from "I want to classify my vault" to "everything is migrated and clean" without needing to reference the plan, brainstorm, or source code. Includes troubleshooting and three real expected-output examples.

**Dependencies:** Units 1–5 (so CLI behaviours, flags, and output formats are stable). RUNBOOK ships in **two passes**: Pass 1 (structure + procedures + troubleshooting) before pilot; Pass 2 (three real expected-output examples) after pilot produces real output.

**Files:**
- `docs/RUNBOOK.md` — new

**Approach (decisions answered from origin §Outstanding Questions):**

Structure:

```markdown
# RUNBOOK — Knowledge Graph Classifier

## Prerequisites
- LM Studio running on :1234 with google/gemma-4-e4b loaded
- Python venv at scripts/classify/venv ready
- Pre-classification backup verified

## Procedures
### 1. Pilot — Job Hunt folder (~35 notes, minutes)
### 2. Sampling and Spot-Check (sample_classified usage)
### 3. AWS Scale-Out (~15h overnight)
### 4. Migration to Flat Vault (after classification)

## Expected Output
### Example 1: a high-confidence rules-classified meeting note
### Example 2: a low-confidence LM-classified interview note with STAR tags
### Example 3: a note that landed in the review queue with operator resolution

## Troubleshooting
(flat list — minimum 8 entries — each entry follows:)

- **Symptom:** what the operator sees
  - **Cause:** what's actually happening
  - **Remedy:** copy-paste commands or steps

Required entries:
- LM Studio unreachable mid-run
- LM Studio slow (calls > 60s)
- Classification rate < 30% (most notes ending in review)
- iCloud sync conflict on a written note
- Process killed mid-run (checkpoint recovery)
- Out of disk space during long run
- Wrong classifications on a specific note pattern
- Heartbeat JSON not appearing

## Reference
- See --help on every CLI for flag specifics
- Plan: docs/plans/2026-05-13-001-feat-obsidian-knowledge-graph-beta-plan.md
- Status snapshot: docs/status-2026-05-14.html
- Decisions log: docs/decisions/decisions.md
```

**Decision on examples:** Use REAL classified notes from the Job Hunt pilot run, sanitised lightly if anything's sensitive. Synthetic examples are portable but feel less concrete and risk drifting from actual output. Real examples bake in personal content but reflect ground truth.

**Decision on troubleshooting format:** Flat list overall; each entry is a mini decision tree via Symptom / Cause / Remedy. Pragmatic middle ground between a global decision tree (too brittle) and unstructured prose (less actionable).

**Test scenarios:** None — pure documentation.

**Verification gate:** Manual read-through after Pass 1. Pass 2 acceptance: operator confirms after pilot that examples and procedures match reality.

---

### Unit 7: Status Page "How to use it" Section

**Execution target: claude**
**Goal:** Extend `docs/status-2026-05-14.html` with a "How to use it" section linking to the RUNBOOK and listing the three most common commands. Keeps the status page complete as a single entry point.

**Dependencies:** Unit 6 (link target must exist).

**Files:**
- `docs/status-2026-05-14.html` — extend; no other files changed

**Approach:**

Insert a new `<section class="section">` between the existing "Vault state" section and the "Operational backlog" section. Content:

- Section-label: "How to use it · day-to-day commands"
- `<h2>`: "Now that the pipeline is built, here's how to actually run it"
- One-paragraph intro: links to RUNBOOK for full procedures
- Three-card mini-grid (reusing existing card / info-card style): "Run the pilot" / "Sample the output" / "Scale to AWS" — each with the single most useful command and a deep-link to the corresponding RUNBOOK section
- Footer link block: "Full procedure, troubleshooting, and examples → [`docs/RUNBOOK.md`](RUNBOOK.md)"

Reuse existing Deep Ocean Tech CSS. No new selectors required.

**Test scenarios:** None.

**Verification gate:** Manual browser review. Plus: `grep -c "How to use it" docs/status-2026-05-14.html` returns ≥ 1.

---

## Test File Map

| Unit | Test file | Type | Net change |
|------|-----------|------|------------|
| 1 | `tests/integration/classify/test_classify_vault.py` (extend) | Integration | +4 tests |
| 2 | `tests/integration/classify/test_classify_vault.py` (extend) | Integration | +3 tests |
| 3 | `tests/integration/classify/test_classify_vault.py` (extend) | Integration | +4 tests |
| 4 | `tests/unit/classify/test_sample_classified.py` (new) | Unit | +7 tests |
| 5 | `tests/unit/classify/test_help_output.py` (new) | Smoke | +4 tests |
| 6 | none (manual review) | Docs | 0 |
| 7 | none (manual review) | Docs | 0 |

Expected post-plan test count: 163 → ~185, all green.

---

## Sequencing

```
Unit 1 (skip-list)              — foundational; ship first
      ↓
Unit 2 (progress bar)           — depends on Unit 1's filtered iter
      ↓
Unit 3 (heartbeat JSON)         — reuses Unit 2's counters
      ↓
Unit 4 (sample CLI)             — independent code, but logical after pipeline updates
      ↓
Unit 5 (--help enrichment)      — picks up new flags from Units 1–4
      ↓
[CHECKPOINT — RUN JOB HUNT PILOT — produces real output for Unit 6 examples]
      ↓
Unit 6 (RUNBOOK Pass 1)         — structure + procedures + troubleshooting BEFORE pilot
Unit 6 (RUNBOOK Pass 2)         — drop in three real examples AFTER pilot
      ↓
Unit 7 (status page section)    — depends on Unit 6 link target
```

Units 1–5 ship as one logical batch (a single PR or commit series; they all touch the classifier package and tests). Unit 6 Pass 1 can ship in parallel with that batch. Pilot runs. Unit 6 Pass 2 + Unit 7 follow.

---

## Deferred to Implementation

- Whether `--filter` should support OR / NOT semantics (v1 = AND-only; revisit if pilot reveals stratification needs).
- Whether `tqdm` should use `unit_scale=True` for the >1000-note AWS run (likely yes; defer to feel during pilot).
- DST handling for `_now_aest()` — AEST/AEDT switch happens twice a year; current implementation uses fixed +10:00 offset. Acceptable until next switch (~2026-10-04 AEDT start); revisit then.

---

## Dependencies / Assumptions

- LM Studio remains on `localhost:1234` with `google/gemma-4-e4b` loaded for any test runs that exercise the LM path.
- The pre-classification backup tarball at `~/Backups/ObsidianVault-pre-classification-2026-05-14.tar.gz` remains valid until pilot is complete.
- The Job Hunt pilot will be run between Units 5 and 6 Pass 2 to provide real example output for the RUNBOOK.
- `tdd-first` and `verification-before-completion` skills are always-active globally; every code-bearing unit follows the cycle (tests before code, full suite green before claiming done).
- Codex routing override discipline from the parent plan's decisions log carries forward — operator may continue running these in Claude until the Codex failure mode is diagnosed.

---

## Success Criteria (from origin)

- **After Job Hunt pilot:** `sample_classified.py --folder "Job Hunt" --n 10` produces a readable terminal report in under 5 seconds; operator can judge "good enough to proceed to AWS" or "needs investigation" in under 2 minutes.
- **During AWS run:** at any moment, operator can either watch the terminal progress bar or `cat .classify_progress.json` from a separate session and get current state. No extra instrumentation needed.
- **Default safety:** `classify_vault.py --vault ~/Documents/ObsidianVault/Personal` (no `--folder`) does NOT touch any note under `wiki/`, verified by an integration test.
- **RUNBOOK quality bar:** a hypothetical second operator can run pilot → review → AWS → migrate end-to-end using ONLY `RUNBOOK.md` plus `--help` output.

---

## System-Wide Impact

- **Interaction graph:** Unit 1's skip-list and Unit 2's tqdm wrapping both intercept the same `_iter_md_files` iterator. Unit 3's heartbeat read by external `cat` or `tail` — atomic write must hold for safe concurrent reads. Unit 4's `sample_classified.py` reuses the same skip-list logic — DRY via a shared helper or careful duplication.
- **Error propagation:** tqdm bars don't suppress exceptions; an LM-Studio timeout still bubbles up to `_classify_note_content`'s try/except and returns the "unavailable" sentinel. Heartbeat writes are best-effort — a write failure should log a warning, not crash the run.
- **State lifecycle risks:** `.classify_progress.json` is overwritten every checkpoint. If the process is killed mid-rename, the `.tmp` file may linger — Unit 3 tests assert post-write cleanup, but a defensive `.tmp` cleanup at run start is recommended.
- **API surface parity:** Skip-list logic must be applied in both `classify_vault._iter_md_files` AND `sample_classified.py`'s file walker. If they drift, sampling could surface wiki/ notes that were never classified. Single shared helper is the right answer.

---

## Sources & References

### Origin

- **Origin document:** [`docs/brainstorms/2026-05-14-pre-pilot-classification-improvements-requirements.md`](../brainstorms/2026-05-14-pre-pilot-classification-improvements-requirements.md) — captures the seven gaps surfaced during pre-pilot review, the brainstorm decisions, and the deferred items.
- **Key decisions carried forward:**
  1. Pilot ships with plain Markdown review queue; tooling decision deferred to post-pilot data.
  2. Hardcoded skip-list over `--safe-mode` flag — defaults must be safe.
  3. tqdm progress bar + flat-dict heartbeat JSON for visibility.
  4. Single comprehensive RUNBOOK over scattered docs.
  5. Five forward-looking concerns (review tooling, correction tracking, per-company MOCs, tag governance, --reclassify, cross-repo sync) explicitly deferred.

### Internal References

- Parent plan: [`docs/plans/2026-05-13-001-feat-obsidian-knowledge-graph-beta-plan.md`](2026-05-13-001-feat-obsidian-knowledge-graph-beta-plan.md)
- Project conventions: [`CLAUDE.md`](../../CLAUDE.md) — venv pytest, atomic writes, LM Studio `tool_choice="required"`
- Decisions log: [`docs/decisions/decisions.md`](../decisions/decisions.md) — includes the Codex-override note that justifies the routing summary
- Handoff log: [`docs/handoff/handoff.md`](../handoff/handoff.md) — operational state and gate
- Routing discipline: global `~/.claude/CLAUDE.md` § "Claude vs Codex Routing"

### External References

- `tqdm` docs: https://tqdm.github.io/ — Unit 2
- Python stdlib `argparse.RawDescriptionHelpFormatter` — Unit 5
