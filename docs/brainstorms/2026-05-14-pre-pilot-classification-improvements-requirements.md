---
date: 2026-05-14
topic: pre-pilot-classification-improvements
---

# Pre-pilot Classification Improvements

## Problem Frame

The 9-unit knowledge-graph classifier plan is code-complete and tested (237 tests passing), but a pre-pilot review surfaced seven gaps between "code works" and "operator can run this confidently on real data". This brainstorm scopes the smallest set of improvements that makes the pipeline pleasant to run, easy to trust, and resilient under the 15-hour AWS scale-out — without over-engineering forward-looking concerns the pilot itself hasn't yet justified.

The Job Hunt pilot (~35 notes) is the next operational step. These improvements ship before that pilot OR alongside it, depending on dependency.

## Requirements

- **R1.** A `sample_classified.py` CLI samples N random auto-classified notes (default N=10) and prints title, key R2 fields, and a body excerpt for spot-checking. Optional `--folder` to scope.
- **R2.** `classify_vault.py` carries a hardcoded skip-list that excludes `wiki/`, `Personal-backup-*/`, `.obsidian/`, `.trash/` from classification regardless of `--folder` / `--vault` arguments. Cannot be overridden via CLI flags. Protects hand-curated content from accidental overwrite of incompatible frontmatter schemas (e.g. wiki's `type: concept`).
- **R3.** `classify_vault.py` renders a live progress bar in the terminal during runs: current/total, percent, running counts (`auto: N | review: M`), ETA, and average LM-call latency when the LM path fires.
- **R4.** `classify_vault.py` writes a heartbeat `.classify_progress.json` to the vault root every 50 notes with current counters, started_at, and last_updated. Same file is written one final time at end-of-run with `complete: true`. Readable via `tail` or any JSON viewer for non-blocking monitoring.
- **R5.** `docs/RUNBOOK.md` exists and covers, with copy-paste commands: pilot procedure, AWS scale-out procedure, sampling workflow, vault migration procedure, troubleshooting (LM Studio down / slow / OOM, iCloud sync conflicts, mid-run process kill + checkpoint recovery, classification quality drops), and at least three expected-output examples (high-confidence rules, LM-classified, review-queue entry).
- **R6.** Every CLI under `scripts/classify/` has a rich `--help` block: one-line summary, full usage example, all flag descriptions, and a "Common patterns" mini-section. The runbook references these via `--help` rather than duplicating.
- **R7.** `docs/status-2026-05-14.html` gains a "How to use it" section that links to `RUNBOOK.md` and lists the three most common commands. Existing content stays.

## Scope Boundaries

Deliberately deferred until the Job Hunt pilot produces real data:

- **Review-queue tooling.** Pilot runs against the plain Markdown table (~12 review items expected; manageable). The decision between interactive CLI walker / extended Flask UI / no-tool gets made after the pilot reveals review-queue shape and volume.
- **Correction-tracking log.** No `corrections.jsonl`, no sentinel field, no learning loop. Corrections are direct frontmatter edits in Obsidian. If post-pilot review reveals systematic errors, revisit.
- **Per-company MOC files.** `Companies.md` keeps the broken-link list for now (Amazon / T-Systems / TSC / Parnell Systems). Per-company MOCs get created lazily after AWS classification, based on actual org volumes. May not need all four.
- **Tag governance.** `TAG_PATTERNS` stays hardcoded. No external config file. Adding a tag continues to require a code change + test update. Acceptable while solo.
- **Re-classification CLI flag.** No `--reclassify-below-N`. If rules change, manual frontmatter delete + re-run works.
- **Cross-repo canonical-name drift check.** `ORG_DOMAINS` (granolaSync) and `ORG_KEYWORDS` (this repo) stay in human-coordinated discipline, documented in both `CLAUDE.md` files.
- **Desktop notifications / Monitor recipe.** Heartbeat JSON is sufficient for visibility; push notifications are overkill for an overnight personal task.

## Success Criteria

- **After Job Hunt pilot:** running `sample_classified.py --folder "Job Hunt" --n 10` produces a readable terminal report in under 5 seconds; the operator can judge "good enough to proceed to AWS" or "needs investigation" in under 2 minutes.
- **During AWS run:** at any moment during the ~15-hour run, the operator can either (a) glance at the terminal and see progress + ETA + auto-vs-review ratio, or (b) `cat .classify_progress.json` from a separate session and get the same data. No need to instrument anything else.
- **Default safety:** `scripts/classify/venv/bin/python scripts/classify/classify_vault.py --vault ~/Documents/ObsidianVault/Personal` (no `--folder`) does not touch any note under `wiki/`. Verified by an integration test.
- **RUNBOOK quality bar:** a hypothetical second operator (or future-you in six months) can run pilot → review → AWS → migrate end-to-end using ONLY `RUNBOOK.md` plus `--help` output. No need to reference the plan, brainstorm, or source code.

## Key Decisions

- **Pilot runs with plain Markdown review queue.** No review-queue tooling pre-built. Decision is data-driven, not speculative. Rationale: pilot volume (~12 items) is small enough for manual; AWS volume (~2,000 items) demands tooling; we don't yet know which tooling shape fits the actual review patterns.
- **Hardcoded skip-list over `--safe-mode` flag.** Lower friction (no extra flag to remember), same protection, harder to bypass accidentally. Rationale: defaults must be safe; user shouldn't have to opt INTO not destroying their wiki.
- **Heartbeat JSON over richer telemetry.** Single file at vault root, no daemon, no notifications. Rationale: the operator running an overnight job will either watch the terminal or check progress in the morning; pager-style alerting is overkill.
- **Single comprehensive RUNBOOK over scattered docs.** One file the operator can grep against, rather than runbook fragments distributed across README + status page + --help. Rationale: troubleshooting is faster when all signals are in one place.

## Dependencies / Assumptions

- LM Studio remains the LM backend (no plan to swap to Ollama or hosted Claude during this phase).
- The Job Hunt folder has not been touched since pre-flight verified its ~35 notes.
- The 2.8 GB pre-classification backup at `~/Backups/ObsidianVault-pre-classification-2026-05-14.tar.gz` remains valid as the recovery point until the post-pilot stage.
- iCloud Drive sync remains the vault's storage substrate (atomic-write discipline already wired into `frontmatter.py`).

## Outstanding Questions

### Resolve Before Planning

(none — all product decisions are made)

### Deferred to Planning

- **[Affects R1][Technical]** Should `sample_classified.py` support `--filter org=Amazon` or `--filter type=meeting` for stratified sampling, or is uniform-random across the matched scope sufficient for v1?
- **[Affects R3][Technical]** Should the progress bar use `tqdm` (new dependency) or a hand-rolled carriage-return updater? `tqdm` is the standard but adds a dep. ~30 LOC of hand-rolled gets the same UX.
- **[Affects R4][Technical]** Format of `.classify_progress.json` — flat dict vs nested per-folder breakdown vs include the last 10 file paths processed? Last-10 is useful for debugging stalls but adds churn.
- **[Affects R5][Needs research]** Should RUNBOOK examples use real classified notes from the user's vault (after pilot) or synthetic / sanitised samples? Real notes give better fidelity but bake in personal content; synthetic is portable but feels less concrete.
- **[Affects R5][Technical]** Should troubleshooting decisions be a flat list or a small decision tree ("if classification rate < 50%, check X then Y")? Decision trees are more useful but more brittle.

## Next Steps

→ `/ce:plan` for structured implementation planning. Recommended unit ordering: scope safety (R2) → progress + heartbeat (R3, R4) → sampling CLI (R1) → RUNBOOK + --help (R5, R6) → status page extension (R7). The first three can ship before pilot; the docs land alongside or just after pilot output validates the format.
