# RUNBOOK — Knowledge Graph Classifier

Operator manual for running the classifier pipeline end-to-end against your real vault. Covers pilot → sampling → AWS scale-out → vault migration, plus troubleshooting and expected output examples.

> **Status**: Pass 1 — structure, procedures, troubleshooting. Pass 2 (3 real classified-note examples) lands after the Job Hunt pilot produces real output.

---

## Prerequisites

Before you run anything below, confirm:

| Check | Command |
|---|---|
| LM Studio running on `:1234` with `google/gemma-4-e4b` loaded | `curl -s http://localhost:1234/v1/models \| jq` |
| Python venv ready with all deps | `scripts/classify/venv/bin/python -c "import openai, yaml, tqdm; print('ok')"` |
| Pre-classification backup exists | `ls -lh ~/Backups/ObsidianVault-pre-classification-*.tar.gz` |
| Both vaults accessible | `ls -d ~/Documents/ObsidianVault/Personal ~/Documents/ObsidianVault/Business` |
| Test suite passes | `scripts/classify/venv/bin/pytest -q` |

If any check fails, fix it before running classification.

---

## Procedures

### 1. Pilot — Job Hunt folder

~35 notes. Runs in minutes. Validates the new `interview` / `management` / `application` / `career` types + tag inference on a small, reviewable sample.

```bash
scripts/classify/venv/bin/python scripts/classify/classify_vault.py \
  --vault ~/Documents/ObsidianVault/Personal \
  --folder "Job Hunt"
```

While it runs you'll see a tqdm progress bar:

```
Classifying: 100%|██████████| 35/35 [00:42<00:00,  0.8note/s, auto:24 | review:11 | lm-avg:2.8s]
```

**Stop conditions during the run** — interrupt with Ctrl-C if you see:
- `auto:0` after the first 5 notes (rules classifier may be misconfigured)
- `lm-avg:` climbing above 60s (LM Studio struggling — check it's loaded)
- Any traceback (treat as a bug, capture stderr, fix before resuming)

**After the run completes**:
- `Personal/classification-review.md` — Markdown table of notes that need manual review
- `Personal/.classify_progress.json` — final run state (`complete: true`)
- `Personal/.classify_checkpoint.json` — list of paths processed (for resume)

Move to step 2.

### 2. Sampling and Spot-Check

Sample 10 random auto-classified notes and eyeball them before deciding to scale to AWS:

```bash
scripts/classify/venv/bin/python scripts/classify/sample_classified.py \
  --vault ~/Documents/ObsidianVault/Personal \
  --folder "Job Hunt" --n 10
```

For each sampled note you'll see title, R2 fields (type/org/context/conf), people, tags, and a 200-char body excerpt.

**Decision gate** — by eye:
- If 9 / 10 look correct → ship it. Proceed to AWS (step 3).
- If 6–8 / 10 look correct → some classifications are wrong but the pipeline is fundamentally OK. Fix the worst via manual frontmatter edit; consider widening rules keywords in `scripts/classify/rules_classifier.py` if a pattern emerges; re-run pilot if you changed rules.
- If <6 / 10 look correct → STOP. Something's wrong (LM Studio temperature, keyword dicts, prompt). Investigate before scaling.

Also check `Personal/classification-review.md` — these are the ones the pipeline already flagged as uncertain. Edit each note's frontmatter manually in Obsidian, then delete it from the review queue file.

### 3. AWS Scale-Out

6,375 notes. ~15 hours of LLM inference (66% rules-classified at <1s each + 33% LM-classified at ~26s each = roughly 14h of LM time + 1h overhead).

**Run pattern A — overnight, single shot**:
```bash
scripts/classify/venv/bin/python scripts/classify/classify_vault.py \
  --vault ~/Documents/ObsidianVault/Personal \
  --folder "Evernote/notes/AWS"
```

Leave the terminal running. The tqdm bar updates live; `.classify_progress.json` is your monitoring file from any other terminal:
```bash
cat ~/Documents/ObsidianVault/Personal/.classify_progress.json
```

**Run pattern B — chunked, multiple sessions** (preferred if you want visible progress without an overnight commitment):
```bash
# Session 1 — first 500 notes
scripts/classify/venv/bin/python scripts/classify/classify_vault.py \
  --vault ~/Documents/ObsidianVault/Personal \
  --folder "Evernote/notes/AWS" --limit 500

# Session 2 — next 500 (already-classified notes skipped automatically)
scripts/classify/venv/bin/python scripts/classify/classify_vault.py \
  --vault ~/Documents/ObsidianVault/Personal \
  --folder "Evernote/notes/AWS" --limit 500

# ...repeat until done
```

**After AWS completes**:
- Spot-check again: `sample_classified --folder "Evernote/notes/AWS" --n 20`
- Inspect `classification-review.md` — likely ~2,000 entries. Don't try to clear it all manually; process opportunistically.
- The other Evernote folders (T-Systems / TSC / Personal NoteBook / Work-General / Cooking) follow the same pattern, smaller volumes.

### 4. Migration to Flat Vault

Once classification is done across the Evernote folders, migrate work-context notes to the Business vault and personal-context notes to the Personal vault root.

**Preview only (default)**:
```bash
scripts/classify/venv/bin/python scripts/classify/migrate_vault.py \
  --personal ~/Documents/ObsidianVault/Personal \
  --business ~/Documents/ObsidianVault/Business
```

You'll see a count: `DRY RUN: to_business=N, to_personal_root=M, skipped_unclassified=K`.

**Apply** — only after preview looks right:
```bash
scripts/classify/venv/bin/python scripts/classify/migrate_vault.py \
  --personal ~/Documents/ObsidianVault/Personal \
  --business ~/Documents/ObsidianVault/Business \
  --confirm
```

Migration log appends to `~/Documents/ObsidianVault/Business/migration-log.md`. Filename collisions get `_2`, `_3` suffixes — nothing is overwritten.

**Staged rollout** — if you want to move only the first 100 to validate:
```bash
... --confirm --limit 100
```

---

## Expected Output (Pass 2 — populated after pilot)

> *To be filled in after the Job Hunt pilot produces real classified output. Three concrete examples will live here:*
> 1. *A high-confidence rules-classified meeting note*
> 2. *A low-confidence LM-classified interview note with STAR tags*
> 3. *A note that landed in the review queue with the operator's resolution*

---

## Troubleshooting

### Symptom: LM Studio unreachable mid-run
- **Cause**: server stopped, port collision, machine slept, or you closed LM Studio by accident
- **Remedy**: Open LM Studio → Local Server → confirm Gemma 4 E4B is loaded → Start Server. Then re-run the same command — `is_classified()` skips already-done notes, so you pick up from where you stopped. Existing `.classify_checkpoint.json` lists what's done.

### Symptom: LM Studio slow (`lm-avg` > 60s consistently)
- **Cause**: model isn't fully GPU-offloaded; LM Studio is doing CPU inference
- **Remedy**: In LM Studio Local Server settings, max out the GPU offload slider. Reload the model. Verify GPU utilisation in Activity Monitor → Window → GPU History.

### Symptom: Classification rate < 30% (most notes ending in review)
- **Cause**: keyword dicts in `scripts/classify/rules_classifier.py` don't match the body content; OR the LM prompt isn't constraining Gemma well
- **Remedy**: Run `sample_classified --filter type=note --n 20` to see which notes got the fallback type. If a pattern emerges (e.g., many AWS notes ending up as `type: note` because they're mostly code), add the missing keywords to `TYPE_KEYWORDS["technical"]`. Re-run with `classify_vault --limit 50` to test.

### Symptom: iCloud sync conflict on a written note
- **Cause**: iCloud reconciliation between two devices touched the file at the same time as the classifier
- **Remedy**: Open the conflicting `<note> (conflicted copy ...).md` in Obsidian, merge frontmatter manually, delete the conflicted copy. The atomic `.tmp`+rename pattern minimises this but can't fully prevent cross-device conflicts. Single-device runs are safest.

### Symptom: Process killed mid-run
- **Cause**: terminal closed, kernel OOM-killer, accidental Ctrl-C, sleep+lid-close, etc.
- **Remedy**: Just re-run the same command. `is_classified()` skips done notes; `.classify_checkpoint.json` knows which paths landed. The heartbeat `.classify_progress.json` shows where you were when killed (it stays at its last snapshot — `complete: false`).

### Symptom: Out of disc space during long run
- **Cause**: review queue + checkpoint + heartbeat + iCloud sync stash
- **Remedy**: Free space; re-run. The classifier writes <1 KB per note's frontmatter, so this is unlikely with a normal-sized vault — but iCloud's local staging can balloon.

### Symptom: Wrong classifications on a specific note pattern
- **Cause**: rules dict doesn't anticipate this pattern; LM hallucinates
- **Remedy**: 
  1. Edit the note's frontmatter directly in Obsidian (correct type / org / context / up). Set `classify_confidence: 1.0` so it doesn't get re-classified.
  2. If the pattern is systematic (e.g., 50+ notes mis-classified the same way), grep the bodies for the common phrase and add it to the matching `TYPE_KEYWORDS` / `ORG_KEYWORDS` entry. Then run the pipeline again — `is_classified()` skips the ones already fixed; new keywords lift others.

### Symptom: Heartbeat `.classify_progress.json` not appearing
- **Cause**: running with `--dry-run` (heartbeat suppressed); or checkpoint_interval hasn't been reached
- **Remedy**: Remove `--dry-run` to enable writes. Heartbeat fires every `checkpoint_interval` (default 50) notes — for tiny runs (Job Hunt with 35 notes) only the final write at end-of-run shows up; that's expected behaviour.

### Symptom: `ModuleNotFoundError: No module named 'scripts'` when running a CLI
- **Cause**: outdated CLI without the sys.path bootstrap, or running from outside repo root
- **Remedy**: After Unit 5 (2026-05-14), all CLIs include a sys.path bootstrap. If you're on older code, run via module form: `python -m scripts.classify.classify_vault --help`. Or pull latest.

### Symptom: Dataview queries in MOCs render as plain code blocks (not tables/lists)
- **Cause**: Dataview plugin not installed or not enabled in the vault you're viewing
- **Remedy**: Open the vault in Obsidian → Settings → Community plugins → Browse → search "Dataview" → Install + Enable. Personal vault has it; Business may need a manual install.

---

## Reference

- **Operator reference (web)**: [`docs/operator-reference.html`](operator-reference.html) — every CLI flag and every progress-bar field. The canonical "how do I run this and what does the output mean" page.
- **CLI specifics**: every command supports `--help`. Each `--help` includes a "Common patterns" section with copy-paste examples.
- **Plan**: [`docs/plans/2026-05-13-001-feat-obsidian-knowledge-graph-beta-plan.md`](plans/2026-05-13-001-feat-obsidian-knowledge-graph-beta-plan.md) — parent plan for the classifier infrastructure
- **Pre-pilot plan**: [`docs/plans/2026-05-14-001-feat-pre-pilot-classification-improvements-plan.md`](plans/2026-05-14-001-feat-pre-pilot-classification-improvements-plan.md) — this plan
- **Status snapshot**: [`docs/status-2026-05-14.html`](status-2026-05-14.html)
- **Decisions log**: [`docs/decisions/decisions.md`](decisions/decisions.md) — why certain choices were made
- **Handoff log**: [`docs/handoff/handoff.md`](handoff/handoff.md) — session-by-session state
