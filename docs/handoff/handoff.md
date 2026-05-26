# Handoff Log

Newest entry at top. Each entry is a resumable snapshot for a fresh Claude or Codex session.

---

## 2026-05-26 NIGHT AEST — ▶ RESUME HERE: body-shape rules shipped, chunk-3 review queue cut 566 → 97 (-83%)

**Runner for next turn:** human (operator). Code stable, v0.3.0 shipped (commit `db11a00`), 387 tests green. Next moves are about the post-chunk operator checklist and deciding whether to add an Anthropic API adapter for the remaining ~7,800 notes.

### State on disc

- **Re-run on AWS folder** (2026-05-26 19:37 → 21:29 AEST, 1h52m): scanned 2834, processed 700 new, auto:541, review:97, **purged:62** (new behaviour), skip:2134, missing:0. lm-calls 327, lm-avg 20.5s. Final stats: ac:85%, rules:57%.
- **AWS corpus progress**: 2,675 / 6,224 classified (43.0%) — up from 34.3% at chunk-3 end. Remaining: 3,549 unclassified.
- **Review queue dropped 566 → 97** (-82.9%) — exactly what the body-shape analysis predicted. New review queue is a healthier mix of `note` (23), `technical` (20), `?` (17), `personal` (15), `meeting` (13), `journal` (9) — genuinely ambiguous cases needing human judgement, not pattern-detection failures.
- **292 notes now carry `type: clipping`** in AWS folder, all routed to `[[Clippings]]` MOC. Sample-checked 10 at random: all genuinely image-only bodies (Skitch screencaps + IMG_*.JPG + Pasted Image), 0 false positives.
- **62 files hard-deleted** this run. Manifest at `~/Documents/ObsidianVault/Personal/.classify_deleted_manifest.json` — 62 entries, all from this run, with path + stripped char count + body preview + run_id.
- **Backups**: pre-classification tarball `~/Backups/ObsidianVault-pre-classification-2026-05-14.tar.gz` (12 days old) is the recovery source for any purge the operator regrets.

### Borderline manifest entries worth a glance

Five purged files where the filename suggests work-relevance even though the body was < 30 chars:

| Path | Body |
|---|---|
| `Evernote/notes/AWS/Best Practices Discussion with Fran.md` | "Tier one- customer impacting" (28 chars) |
| `Evernote/notes/AWS/Contour Sprint 15 Planning.md` | "Runbooks" (8 chars) |
| `Evernote/notes/AWS/Deep Dive_ Review.md` | "1. Randomising" (14 chars) |
| `Evernote/notes/AWS/Peer Feedback - 2015.md` | "- [ ] Anthony Surez" (17 chars) |
| `Evernote/notes/AWS/Planning for Region Sync.md` | "Ordering of service builds" (26 chars) |

Recoverable from the backup tarball if any of them turn out to have been needed.

### What landed this session

- **Plan**: `docs/plans/2026-05-26-001-feat-body-shape-classifier-rules-plan.md`
- **Code (commit db11a00)**: 4 body-shape regex rules in `rules_classifier.py`, `_classify_by_body_shape()` + `should_purge_by_body_shape()` helpers, new `clipping` type in `UP_MAP` → `[[Clippings]]` MOC, restructured per-note loop in `classify_vault.py` (rules → purge gate → LM cascade), atomic manifest writer, `purged` counter threaded through summary + heartbeat + tqdm postfix.
- **Tests**: 353 → 387 passing. New classes: `TestBodyShapeClippingRules`, `TestShouldPurgeByBodyShape`, `TestBodyShapeReason`, `TestTinyBodyDeletion`, `TestBodyShapeOrdering`. Six pre-existing tests updated where tiny convenience bodies would have triggered the new purge gate.
- **Version**: `pyproject.toml` 0.2.3 → 0.3.0 (minor — new behaviour, no breaking changes). CHANGELOG entry `[0.3.0]` added.
- **Operator docs**: `docs/2026-05-26-post-chunk-operator-checklist.md` (4-step post-run workflow: audit manifest → triage queue → prune Clippings → decide next chunk). `docs/RUNBOOK.md` cross-references it.
- **Project memory saved**: `project_north_star.md` — "categorise for interview prep + lean delete for noise reduction".

### Stats trend (chunks 1 → 4)

| Chunk | Date | Folder | Notes | auto-rate | rules-catch | review-queue % | purged | lm-avg |
|---|---|---|---|---|---|---|---|---|
| 1 | 2026-05-14 AM | Job Hunt | 16 | 100% | 0% | 0% | 0 | 26.2s |
| 2 | 2026-05-14 PM | AWS | 691 | 73% | 10% | 27% | 0 | 8.4s |
| 3 | 2026-05-15 AM | AWS | 2000 | 72% | 13% | 28% | 0 | 9.4s |
| **4** | **2026-05-26 PM** | **AWS** | **700** | **85%** | **57%** | **14%** | **62** | **20.5s** |

Headlines: review-queue ratio halved (28% → 14%), purge gate kicked in (62 deletions), rules-catch quadrupled (13% → 57% — body-shape rules doing their job). LM avg went UP (9.4s → 20.5s) — possibly LM Studio memory drift over the 1h52m run, worth a quick restart before the next chunk.

### Where to focus next (operator)

**Immediate (post-run operator checklist, ~45–60 min):**
1. Run the audit script in `docs/2026-05-26-post-chunk-operator-checklist.md` Step 1 — eyeball the 62 manifest entries. Restore any of the 5 borderline ones if they look career-relevant.
2. Open the new `classification-review.html` (97 cards) — triage via the helper-server bulk-delete UI. Most should resolve in 30 min.
3. Browse `[[Clippings]]` in Obsidian. ~292 entries; most are pre-2020 Skitch screencaps with no recent reference value. Bulk-delete in Finder what you don't want.

**Operational decision (not urgent):**
- LM is now the bottleneck — 327 LM calls × 20.5s = ~1h52m of LM-bound time per 700-note chunk. With ~3,549 AWS notes remaining + ~4,000 elsewhere = ~7,500 more notes. At current rates that's ~6 chunks × ~2h each = 12h+ of additional runtime.
- **Drafted but not built**: an Anthropic API adapter (`anthropic_classifier.py` + `--api anthropic` CLI flag). Would cut LM call latency from ~20s to ~1–3s, finishing the remaining vault in ~40 min wall-clock for ~$8 total cost. Trade-off: notes that don't hit the rules cascade get sent to Anthropic (privacy consideration). Worth a fast plan + build session if the operator wants the speed-up.

### Next chunk command (drafted, not auto-launched per binding runner=human rule)

Once the operator checklist is complete, the next AWS chunk:

```bash
# Restart LM Studio first if lm-avg is climbing (memory drift)
scripts/classify/venv/bin/python scripts/classify/classify_vault.py \
  --vault ~/Documents/ObsidianVault/Personal \
  --folder "Evernote/notes/AWS" \
  --limit 2000 --html
```

At ac:85% / rules:57%, a 2000-note chunk should produce ~1700 auto-classify + ~180 purge + ~280 review queue, finishing in ~3–4h. If `--limit 2000` feels too long, `--limit 1000` is the conservative call.

### Untracked file

- `AGENTS.md` (operator-authored, sitting since project start, never committed). Up to the operator whether to track it.

---

## 2026-05-15 EARLY-AM AEST — ▶ RESUME HERE: AWS chunk 3 complete, FileNotFoundError race patched, operator-reference page live

**Runner for next turn:** human (operator). Code stable. Triage backlog growing; rules-catch low. Next moves are about reducing review-queue debt, not adding more chunks.

### State on disc

- **AWS chunk 3** (2026-05-14 21:43 → 2026-05-15 02:09 AEST, ~4h27m): scanned 2000, auto:1434, review:566, skip:690, missing:0, lm-avg 9.4s, rules-catch 13%, ac-rate 72%. Clean exit.
- **AWS corpus progress**: 2124 / 6363 classified (33.4%). Vault file count dropped from 6375 → 6363 because operator deleted ~12 stale notes during chunk-2 review-queue triage.
- **Combined review queue across all chunks**: ~700+ notes awaiting manual triage (136 from chunk 2 archived at `classification-review-2026-05-14-pm.html`, then 566 from chunk 3 in the current `classification-review.html`). This is now the dominant operational debt.
- **Backup**: `~/Backups/ObsidianVault-pre-classification-2026-05-14.tar.gz` (2.8 GB) still intact.

### What landed this session

- **FileNotFoundError race patch** in `classify_vault.py`. Pre-scan (`_count_already_classified`) and main loop body both wrap file-touching code in `try/except FileNotFoundError → skip`. New `skipped_missing` counter threaded through postfix (`missing:N` segment), `.classify_progress.json` heartbeat (`totals.skipped_missing`), summary dict, and CLI summary print. Fixes the chunk-3 first-attempt crash where a file deleted by parallel operator triage killed the whole run at iteration 33. Tests: new `TestClassifyVaultRaceConditions` class with 3 tests covering single vanish, heartbeat reporting, multiple vanished files.
- **Test suite**: 286 → 289 passed, 0 failed.
- **`docs/operator-reference.html`** (new, 39 KB). Single-page reference: every CLI flag for `classify_vault.py` / `sample_classified.py` / `fix_evernote_titles.py` / `migrate_vault.py`, the progress-bar field-by-field reference (12 cards), the output-review guide, and three decision gates. Linked from the index hub (replaces the stale "Classifier source" card pointing at the Ollama-era `classify_notes.py`) and from status-2026-05-14.html.
- **Project-local memory**: `feedback_handoff_runner_tag.md` saved — when handoff tags runner=human, classifier batches must be drafted not auto-launched. Captures the 2026-05-14 PM mis-execution.
- **Two commits pushed to `origin/main`**: `feat(classify): pre-pilot classifier hardening + race tolerance` (code/tests) and a docs commit (operator-reference + index + status + RUNBOOK + this handoff entry).

### Stats trend (chunks 1, 2, 3)

| Chunk | Date | LM avg | Auto-rate | Rules catch | Review-queue ratio |
|---|---|---|---|---|---|
| 1 (Job Hunt) | 2026-05-14 AM | 26.2s | 100% | 0% | 0% |
| 2 (AWS) | 2026-05-14 PM | 8.4s | 73% | 10% | 27% |
| 3 (AWS) | 2026-05-15 AM | 9.4s | 72% | 13% | 28% |

Pattern: LM latency stabilised post-FD-leak fix. Auto-rate and rules-catch holding. Review-queue is the leverage point — climbing 13% rules-catch is the next compounding win.

### Where to focus before chunk 4

1. **Mine the review queue for rule patterns** — open `classification-review.html`, look for clusters by title pattern (re:Invent sessions, "Reading list", screenshots, dated standup logs, calibration cycles, OLR templates) and bump matching patterns into `_TITLE_TYPE_RULES` in `rules_classifier.py`. Each rule moves N future notes from LM-burdened review-queue candidates to free, instant, auto-classified.
2. **Triage the chunk-3 review queue** — 566 notes. The faster you drain this, the more honest the rules-catch lift will be on chunk 4.
3. **Consider the helper-server idea** (see chat history): tiny local FastAPI/stdlib HTTP server so the review HTML can POST delete/reclassify actions. Builds on the patch — `missing:N` will harmlessly tick up during simultaneous batch + triage.
4. **CHANGELOG.md still absent**. Project has `version = "0.1.0"` in `pyproject.toml` but no CHANGELOG yet. Worth bootstrapping per global Versioning Discipline rule before the next batch of behaviour-changing commits.

### Next chunk command (unchanged)

```bash
cd ~/Documents/VSStudio/personal/evernote-to-obsidian
scripts/classify/venv/bin/python scripts/classify/classify_vault.py \
  --vault ~/Documents/ObsidianVault/Personal \
  --folder "Evernote/notes/AWS" \
  --limit 2000 --html
```

Estimated runtime: another ~4.5h chunk gets us to ~50% AWS done.

---

## 2026-05-14 EVENING AEST — AWS chunk 2 complete, ~5600 unclassified left (superseded by entry above)

**Runner for next turn:** human (operator). Code is stable, classifier is calibrated. Continue chunking AWS, then drop `--folder` to sweep the rest of the Personal vault.

### State on disc

- **691 AWS notes classified** (327 from morning + 364 from evening chunk). Personal vault total classified: ~707 (16 Job Hunt + 691 AWS).
- **AWS remainder**: ~5,684 unclassified. At observed 8.4 sec/LM-call + 10% rules catch + 27% review rate, projected ~10–11 hours of LM time.
- **Personal vault total**: ~10,621 .md files; ~10,500 require classification (minus wiki/, raw/, _resources/).
- **136 notes** in the latest chunk's review queue (`classification-review.html` open in browser).
- **Backup tarball**: `~/Backups/ObsidianVault-pre-classification-2026-05-14.tar.gz` (2.8 GB) — intact, safe rollback path.

### What landed this session (in addition to morning's parser hardening + title fixer)

- **FD-leak fix in `lm_classifier.py`.** `openai.OpenAI()` was being instantiated per call → httpx connection-pool leak → crash at ~297 LM calls. Replaced with `functools.lru_cache(maxsize=1)` singleton. Regression test in `tests/unit/classify/test_lm_classifier.py::TestSingletonClientLifecycle`. Side effect: LM avg dropped from 18.7 sec → 8.4 sec (connection-pool reuse).
- **HTML audit output.** New `scripts/classify/html_renderer.py` (~270 lines, 12 unit tests). Self-contained dark-themed HTML with `obsidian://open` click-through links. `--html` flag on `classify_vault.py` writes `classification-review.html` alongside the .md. `--html PATH` flag on `sample_classified.py` writes a sample report to a chosen path.
- **Rules cascade overhaul.** New `_TITLE_TYPE_RULES` list (1-1, standup, weekly sync, sprint, interview, OLR/PIP, calibration, goals, re:Invent, summit, roadmap, screenshot, SKO, yearly). Folder-hint org confidence bumped 0.5 → 0.95. Min-keyword-score gate (≥2 keywords required, single-keyword matches drop to 0.5 confidence). Noisy interview/career keywords trimmed. 25 new tests. AWS rules-catch went from 0% → 10% in production.
- **Progress bar overhaul** in `classify_vault.py`. Bar now tracks ACTUAL classifications (not iterations through file_list). New postfix segments: `skip:N`, `ac:X%`, `rules:X%`, `corpus-eta:Xh`. 12 new unit tests.
- **Tests:** 286 passed, 3 deselected (live LM), 0 failed. (Up from 209 at session start.)

### Real chunk performance (2026-05-14 19:29–20:32)

```json
{
  "scanned": 827, "auto_classified": 364, "needs_review": 136,
  "skipped_already_classified": 327, "lm_calls": 450,
  "lm_call_avg_seconds": 8.4
}
```

500-note chunk in ~1 hour, clean exit. Rules: 50 of 500 attempts caught without LM (~10%). LM auto-rate: 73% (310 auto-from-LM out of 450 LM calls). Review rate: 27%. These numbers are calibration-baseline going forward.

### Two review commands per chunk

```bash
# Spot-check confident classifications (different seed each time)
scripts/classify/venv/bin/python scripts/classify/sample_classified.py \
  --vault ~/Documents/ObsidianVault/Personal \
  --folder "Evernote/notes/AWS" --n 20 --seed <new-number> \
  --html ~/Documents/ObsidianVault/Personal/sample_classified.html
open ~/Documents/ObsidianVault/Personal/sample_classified.html

# Review the review queue
open ~/Documents/ObsidianVault/Personal/classification-review.html
```

### Next chunk command

```bash
cd ~/Documents/VSStudio/personal/evernote-to-obsidian
scripts/classify/venv/bin/python scripts/classify/classify_vault.py \
  --vault ~/Documents/ObsidianVault/Personal \
  --folder "Evernote/notes/AWS" \
  --limit 500 --html
```

Bigger chunks are fine now that the FD leak is fixed — `--limit 2000` would be a ~3.3-hour overnight chunk.

When AWS is done, drop `--folder` to sweep T-Systems / Personal NoteBook / TSC / Cooking / etc.

### Operational backlog (after AWS is classified)

1. ~~Smoke-test MOC inbox pattern.~~ Done — Dataview Cheatsheet + working inbox blocks verified.
2. ~~Install Dataview in Business vault.~~ Done — both vaults have it.
3. ~~Stage 0a Job Hunt pilot.~~ Done.
4. **Stage 0b — finish vault-wide classification.** In progress (691/10,500 done; ~5,684 AWS + ~4,160 non-AWS remaining).
5. **Triage the review queue.** Combined across runs (~163 review-queue notes total: 27 from AM Job Hunt + 136 from PM AWS). Manual: open `classification-review.html`, add the correct `up:` frontmatter or delete the note.
6. **Unit 8 — `migrate_vault.py`** moves classified work notes to Business vault. Default dry-run; pass `--confirm`.
7. **Decide about legacy `Personal/Meetings/Meetings Homepage.md`** (Granola's `regenerate_index` still writes to it).

### Uncommitted changes — substantial

In addition to morning's uncommitted state:
- `scripts/classify/lm_classifier.py` — singleton client
- `scripts/classify/classify_vault.py` — bar fix + 4 new postfix segments + manual tqdm + checkpoint logic untouched
- `scripts/classify/rules_classifier.py` — title rules + folder boost + min-score gate + trimmed keywords
- `scripts/classify/html_renderer.py` — new (~270 lines)
- `scripts/classify/fix_evernote_titles.py` — new (~200 lines, from AM)
- Tests: `test_lm_classifier.py` (+singleton tests), `test_rules_classifier.py` (+25 tests), `test_classify_vault_helpers.py` (new, 25 tests), `test_html_renderer.py` (new, 12 tests), `test_frontmatter.py` (+6 tests for tolerance), `test_fix_evernote_titles.py` (new, 12 tests)
- Cumulative: **691 AWS notes** classified on disc via `up:` frontmatter (these are user data, not code)
- Cumulative: **1,540 AWS note titles** quoted in YAML frontmatter (from AM session's title fixer)

User has not committed any of this yet. Consider a multi-commit split if/when they do (one per logical change).

---

## 2026-05-14 PM AEST — pipeline unblocked, AWS ready for classify (superseded by entry above)

**Runner for next turn:** human (operator). Code + data fixes done; the next step is running the classifier on AWS in chunks.

### What landed this session

- **`scripts/classify/frontmatter.py` hardened.** `_split()` now catches `yaml.YAMLError` and returns `{}`/text instead of crashing the pipeline. Same defence applies transitively to `read_frontmatter`, `is_classified`, `write_frontmatter`. Six new tests in `tests/unit/classify/test_frontmatter.py::TestReadFrontmatterMalformedYAML` lock the behaviour.
- **`scripts/classify/fix_evernote_titles.py` new.** One-shot script that quotes unquoted Evernote-export titles. Single-quote style with apostrophe-doubling per YAML spec. Skip-list shared with `classify_vault.py` (reuses `_iter_md_files`). Atomic write + 50 ms iCloud sleep per file. 12 unit tests in `tests/unit/classify/test_fix_evernote_titles.py`.
- **Applied to all of Evernote/notes/AWS.** 1,540 / 6,375 titles fixed in 88 sec. `unfixable=0`. Re-scan confirms 0 YAML parse failures across all 6,375 AWS notes.
- **`sample_classified.py` now runs cleanly on AWS.** Returns "0 classified notes" (correct — AWS hasn't been classified yet), no traceback.
- **HTML review output** added to both `classify_vault.py --html` (writes `classification-review.html`) and `sample_classified.py --html PATH` (writes sample report HTML). Self-contained, dark theme, click-through `obsidian://open` links, confidence-bucketed badges. New `scripts/classify/html_renderer.py` module (~270 lines) with 12 unit tests.
- **Progress bar overhaul** in `classify_vault.py`:
  - Bar denominator now respects `--limit` (was always full folder size). New `_progress_total` helper, 5 unit tests.
  - Postfix now includes corpus-overall progress as a second signal: `auto:N | review:N | lm-avg:Xs | overall: X/Y (Z.Z%)`. The overall count is `corpus_classified_at_start + auto_classified_this_run`. Pre-scan via new `_count_already_classified` helper (~3 sec for 6,375 files). New `_overall_postfix` helper. 8 unit tests across both helpers.
- **Tests:** 234 passed, 3 deselected (live LM Studio tests), 0 failed.

### Bug context (so the next session understands the shape)

Evernote .enex → markdown export wrote `title:` values raw — e.g. `title: 1-1: Stefan`, `title: - Business Card`, `title: * [[link]]`. YAML treats those as structural (`:` = mapping, `-` = sequence, `*` = alias) and `yaml.safe_load` correctly rejected them. 100% of failures (1,540/1,540) were title-line only; no other field was malformed. The fix is purely cosmetic (wraps the title value in single quotes) — round-trip preserves the original string verbatim.

### What's NOT yet done (still the operational backlog)

1. ~~Smoke-test the MOC inbox pattern.~~ Partially validated. Job Hunt.md's malformed dataview block was fixed this session; Interview Prep.md confirmed rendering correctly.
2. ~~Install Dataview in Business vault.~~ Done — verified, both vaults have it.
3. ~~Stage 0a pilot — Job Hunt folder.~~ Done in the AM run. 16/16 auto-classified, 0 review queue, confidence 0.9–1.0. Two debatable routing calls noted: `_Dashboard.md` typed as `application` (meta-tracker), `LP Quick-Reference — Amazon Leadership Principles.md` routed to `[[Personal]]` (probably should be `[[Interview Prep]]`). Acceptable; not blocking AWS.
4. **Stage 0b — AWS classification.** Now unblocked. Run in chunks for monitoring. Time estimate: ~46h LM-only if every note hits the LM (Job Hunt pilot ran 16/16 through LM at avg 26.2 sec); AWS may run faster if `type: technical` content trips the rules cascade more often. **First chunk should be small (e.g. `--limit 100`)** so the operator can audit before scaling. Audit signals after each chunk:
   - `classification-review.md` — review queue (low-confidence)
   - `.classify_progress.json` — totals + per-call timing
   - `sample_classified.py --folder "Evernote/notes/AWS" --n 20 --seed 42` — spot-check high-confidence calls that won't appear in the review queue
   - Open `Reference.md`, `Personal.md`, `Technical.md` (Business) MOCs in Obsidian — inbox blocks should populate
5. Unit 8 — `migrate_vault.py` moves work notes to Business after classification. Default dry-run; pass `--confirm` to actually move.
6. Decide about legacy `Personal/Meetings/Meetings Homepage.md` (granolaSync's `regenerate_index` still writes to it).

### Concrete next command

```bash
cd ~/Documents/VSStudio/personal/evernote-to-obsidian
scripts/classify/venv/bin/python scripts/classify/classify_vault.py \
  --vault ~/Documents/ObsidianVault/Personal \
  --folder "Evernote/notes/AWS" --limit 100
```

Then audit:
```bash
cat ~/Documents/ObsidianVault/Personal/classification-review.md
cat ~/Documents/ObsidianVault/Personal/.classify_progress.json
scripts/classify/venv/bin/python scripts/classify/sample_classified.py \
  --vault ~/Documents/ObsidianVault/Personal \
  --folder "Evernote/notes/AWS" --n 20 --seed 42
```

### Uncommitted changes (substantial)

In addition to the AM session's uncommitted state:
- `scripts/classify/frontmatter.py` — try/except around yaml.safe_load
- `scripts/classify/fix_evernote_titles.py` — new file (~200 lines)
- `tests/unit/classify/test_frontmatter.py` — +6 tests
- `tests/unit/classify/test_fix_evernote_titles.py` — new file (12 tests)
- **1,540 modified files under `~/Documents/ObsidianVault/Personal/Evernote/notes/AWS/`** — title-line edits only. Backup at `~/Backups/ObsidianVault-pre-classification-2026-05-14.tar.gz` (2.8 GB) intact.

### Other small fixes this session

- `docs/handoff/handoff.md` earlier "install Dataview in Business" claim corrected (was already installed).
- `~/Documents/ObsidianVault/Personal/Job Hunt.md` had a paste-corrupted dataview block (line 9 with collapsed fence) — fixed.
- New reference doc: `~/Documents/ObsidianVault/Personal/tools/Dataview Cheatsheet.md` — 10 common dataview queries scoped to this vault's R2 schema.

---

## 2026-05-14 AM AEST — ALL 9 plan units done — pilot is the next operational step (superseded by entry above)

**Runner for next turn:** human (operator). The code is done; the next step is running the classifier against the Job Hunt pilot, then reviewing the output before scaling to AWS.

### Plan status: every unit complete

| Unit | Code | Tests | Verified |
|---|---|---|---|
| 0 — LM Studio verify | n/a | curl JSON parsed | ✅ |
| 0.5 — Backup | n/a | 2.8 GB tarball | ✅ |
| 1 — venv + deps | ✅ | import smoke | ✅ |
| 2 — frontmatter.py | ✅ | 14 unit tests | ✅ |
| 3 — rules_classifier.py | ✅ | 13 unit tests | ✅ |
| 4 — lm_classifier.py | ✅ | 6 mocked + 3 live | ✅ |
| 5 — classify_vault.py | ✅ | 13 integration | ✅ |
| 6 — Granola R2 schema | ✅ | 16 unit (granolaSync) | ✅ |
| 7 — 16 MOCs + legacy rewriter | ✅ | 6 unit + manual | ✅ |
| 8 — migrate_vault.py | ✅ | 9 integration | ✅ |

**Final test counts:**
- `evernote-to-obsidian`: 163 passed (3 live deselected) via `scripts/classify/venv/bin/pytest -q`
- `granolaSync`: 74 passed via bare `pytest`
- Live integration: 3 passed against running LM Studio when invoked with `-m integration_live`

### Real-vault changes already applied during the session

- ✅ **16 MOC files written** to vault roots:
  - Personal: Home, Meetings, Personal, People, Reference, Interview Prep, Job Hunt, Career
  - Business: Home, Meetings, Technical, Companies, People, Projects, Leadership, Patterns
- ✅ **8 legacy `up:` links rewritten** in `Personal/Meetings/` (Granola notes now point at `[[Meetings]]`, not `[[Meetings Homepage]]`). `grep -r '[[Meetings Homepage]]' ~/Documents/ObsidianVault/Personal` returns nothing.
- ✅ **Backup tarball intact** at `~/Backups/ObsidianVault-pre-classification-2026-05-14.tar.gz` (2.8 GB).

### What's NOT yet done (this is the operational backlog)

These are deliberate gating steps — the plan said classify before migrate, pilot before AWS.

1. **Smoke-test the MOC inbox pattern in Obsidian.** Open `Personal/Meetings.md`, create a throwaway note with `up: "[[Meetings]]"`, confirm it appears in the Dataview LIST within ~2s. Repeat for `Job Hunt.md` and `Interview Prep.md`. (Partially validated 2026-05-14 PM: dataview block renders correctly on Interview Prep; Job Hunt.md had a malformed paste-corrupted block, now fixed.)
2. ~~**Install Dataview in the Business vault.**~~ **Done** — verified 2026-05-14 AEST. `Business/.obsidian/community-plugins.json` lists `dataview`, plugin folder present in both vaults. Earlier "missing" claim was a stale pre-flight note.
3. ~~**Stage 0a pilot — classify the Job Hunt folder.**~~ **Done** — 2026-05-14 11:52–11:59 AEST. 16/16 auto-classified, 0 in review queue, all confidence ≥ 0.9 (1× 0.9, 13× 0.95, 2× 1.0). LM was called 16/16 times (rules cascade caught nothing in Job Hunt) at avg 26.2 sec/call. Type distribution: 10 interview, 4 note, 2 application. Routing distribution: 10 `[[Interview Prep]]`, 4 `[[Personal]]`, 2 `[[Job Hunt]]`. Spot-check flagged two debatable calls: `_Dashboard.md` typed as `application` (it's a meta-tracker) and `LP Quick-Reference — Amazon Leadership Principles.md` typed as `note → [[Personal]]` (probably should be `interview → [[Interview Prep]]`).
4. **Stage 0b — classify Evernote/notes/AWS** (6,375 notes). **Revised time estimate: ~46h LM inference**, not 15h — from the pilot's measured 26.2 sec/note × 6,375. AWS may be faster if the rules cascade catches more `type: technical` content there than it did in Job Hunt. Plan 2–3 overnight runs, chunked with `--limit`. First chunk should be small (e.g. `--limit 100`) so the user can audit before scaling. Audit signals after each chunk: `classification-review.md` (review queue), `.classify_progress.json` (totals + per-call timing), and `sample_classified.py --folder "Evernote/notes/AWS"` for spot-checking high-confidence calls that won't appear in the review queue.
5. **Then Unit 8 — migrate_vault** moves classified work notes to Business, classified personal notes to Personal root. Default is dry-run; pass `--confirm` to actually move.
6. **Decide about the legacy `Personal/Meetings/Meetings Homepage.md`.** The granolaSync `regenerate_index` function still writes to it on every Granola sync. Either delete it manually (the new `Meetings.md` MOC supersedes it) and disable `regenerate_index` calls, OR leave both for redundancy.

### Routing decision recorded

All units 4–8 were executed by Claude despite codex-delegate tags. Two Codex attempts produced no files on disc (verified by `find` returning empty). User chose Claude for remainder. See `docs/decisions/decisions.md` 2026-05-14 entry. Future planning should route back to Codex only after diagnosing the Codex failure mode.

### Uncommitted changes

The repo has substantial uncommitted state across:
- New module: `scripts/classify/` (6 .py files + venv)
- New tests: `tests/unit/classify/`, `tests/integration/classify/`
- Plan + handoff + decisions log updates
- granolaSync `export_granola.py` extension + new tests

Decision to commit deferred to user. Suggested split if committing: one commit per unit (clean log) or one big "implement classifier pipeline" commit for evernote-to-obsidian + a separate commit in granolaSync for the export schema additions.

### Environment recap

- LM Studio: `google/gemma-4-e4b` on `http://localhost:1234/v1`, `tool_choice="required"` (string, not object)
- Python venv: `evernote-to-obsidian/scripts/classify/venv/`
- Test runner for classify suite: `scripts/classify/venv/bin/pytest` (bare `pytest` can't see PyYAML)
- iCloud Drive: vaults live under `~/Documents/`; atomic writes + 50ms sleep already wired into Units 2 and 5

---

## 2026-05-14 AEST — Units 0–3 done, ready for Unit 4 (superseded by entry above)

**Runner for next turn:** plan tags Unit 4 as `codex-delegate`; user has been overriding to Claude for the small/contained ones — ask before starting.

**Where things stand:**

| Unit | Status | What landed |
|---|---|---|
| 0 | ✅ | LM Studio + Gemma 4 E4B verified; tool_choice gotcha recorded |
| 0.5 | ✅ | `~/Backups/ObsidianVault-pre-classification-2026-05-14.tar.gz` (2.8 GB) |
| 1 | ✅ | `scripts/classify/{__init__.py, requirements.txt, venv/}` — `openai==2.36.0`, `PyYAML==6.0.3`, `pytest==9.0.3` |
| 2 | ✅ | `scripts/classify/frontmatter.py` + 14 tests (read/write/is_classified, atomic .tmp+rename) |
| 3 | ✅ | `scripts/classify/rules_classifier.py` + 13 tests (full R2 schema: type/org/context/people/tags/confidence) |

**Test suite:** 129/129 passed via `scripts/classify/venv/bin/pytest -q`.

### Decisions recorded this session (see `docs/decisions/decisions.md`)
1. Classifier code in `evernote-to-obsidian/scripts/classify/` (not granolaSync).
2. LM Studio `tool_choice` requires string form (`"required"`), not the OpenAI object form.
3. Classify tests run via venv pytest because Homebrew pytest's libexec Python has no pip.

### Unit 4 spec (next)

`scripts/classify/lm_classifier.py` — LM Studio classifier via Gemma 4 E4B function calling. Use:
- `LM_STUDIO_BASE_URL = "http://localhost:1234/v1"`
- `LM_STUDIO_MODEL = "google/gemma-4-e4b"` (verified Unit 0)
- `openai.OpenAI(base_url=..., api_key="lm-studio")`
- `tool_choice="required"` (string, not object — verified Unit 0)
- `client.chat.completions.create(...)` with the full enum-constrained schema from plan §Unit 4
- Parse `tool_calls[0].function.arguments` via `json.loads()`
- On ANY exception: return `{"confidence": 0.0, "reason": "lm-studio unavailable", ...}` — never raise
- Mocked tests in `tests/unit/classify/test_lm_classifier.py`
- Live smoke test in `tests/integration/classify/test_lm_classifier_live.py` marked `integration_live`, skipped by default

Verification gate: `scripts/classify/venv/bin/pytest tests/unit/classify/test_lm_classifier.py -v` — all pass. Then optionally run the live test against the LM Studio server.

### Uncommitted changes

Plan doc, handoff, decisions log, and the new code/tests are all uncommitted. Decision to commit deferred to user.

### Environment gotchas (unchanged)

- Python 3.14 Homebrew, pip blocked system-wide — venv required
- Use `scripts/classify/venv/bin/pytest` for any test that imports yaml or openai
- iCloud Drive under `~/Documents/` — atomic writes + 50ms inter-file sleep during bulk classification
- LM Studio must be running on :1234 for the Unit 4 live smoke test

---

## 2026-05-14 AEST — Units 0 + 0.5 done, ready for Unit 1 (codex-delegate)

**Runner for next turn:** Codex — Unit 1 is `codex-delegate` (mechanical venv + requirements scaffolding).

**TL;DR:**
Pre-flight is clean. Unit 0 (LM Studio verification) and Unit 0.5 (vault backup) are both verified PASS. Plan doc has been path-rewritten for the structural decision (Option B — classifier code lives in `evernote-to-obsidian/scripts/classify/`, not granolaSync). Next step is Unit 1: create the venv + requirements.txt at `evernote-to-obsidian/scripts/classify/`.

### Unit 0 PASS evidence (LM Studio + Gemma 4 E4B)

- LM Studio Local Server running on `http://localhost:1234/v1`
- `/v1/models` returns `google/gemma-4-e4b` (this is the canonical `LM_STUDIO_MODEL` value for Unit 4)
- Function-calling smoke test (single-tool prompt with `classify_note` schema) returned `tool_calls[0].function.arguments` as parseable JSON with all four required fields. `confidence` was a float (0.9), not a string. ✅

**Plan gotcha discovered & fixed:** LM Studio's chat-completions endpoint **rejects** OpenAI-style object `tool_choice` with HTTP 400 `Invalid tool_choice type: 'object'`. Only string values are accepted: `none`, `auto`, `required`. Plan Unit 4 is now updated to use `tool_choice="required"` (functionally identical when only one tool is exposed). Codex implementing Unit 4 should use the string form.

**Quality caveat noted:** With a permissive schema (no `enum` constraints), Gemma returned non-canonical values like `org: "Tech/IT"`. Unit 4's full schema uses `enum` constraints which should anchor the output. Validate this in the live integration test (Unit 4 spec already includes `test_lm_classifier_live.py`).

### Unit 0.5 PASS evidence (vault backup)

- Backup file: `~/Backups/ObsidianVault-pre-classification-2026-05-14.tar.gz` — 2.8 GB
- Contains 16,834 entries under `ObsidianVault/Personal/` and 30 under `ObsidianVault/Business/`
- Restore: `mv ~/Documents/ObsidianVault ~/Documents/ObsidianVault.broken && tar -xzf ~/Backups/ObsidianVault-pre-classification-2026-05-14.tar.gz -C ~/Documents/`

**Observation:** Business vault is sparse (30 entries vs. 16,834 in Personal). Worth checking before scaling Unit 7 in Business — it may be that most Business work currently sits in `Personal/Evernote/notes/AWS/` and needs to be migrated by Unit 8 *before* Business MOCs are useful. Doesn't change unit sequencing; just sizes expectations.

### Pre-flight findings that became real changes

1. **Plan path rewrite (Option B)** — done. All Unit 1–5, 7, 8 paths now read `evernote-to-obsidian/scripts/classify/` and `evernote-to-obsidian/tests/`. Unit 6 (Granola export) stays in granolaSync. Added a `## Path Layout` section to the plan documenting this.
2. **Business vault Dataview** — was missing. User said they'll install it; do not start Unit 7 until installed. (Personal vault Dataview v0.5.68 still installed.)
3. **Meetings Homepage** — NOT at Personal vault root; lives at `Personal/Meetings/Meetings Homepage.md` with 8 Granola notes around it. Unit 7's sed rewriter (recursive find) handles the `up:` link fine, but the *file moves* (Granola notes → vault root, kill the `Meetings/` subfolder) are picked up by Unit 8's defrag pass. Empty stub `Personal/Meetings.md` at vault root will be overwritten by Unit 7's MOC generation. Tarball also showed a third location `~/Documents/ObsidianVault/Meetings/` at the ObsidianVault root — worth investigating in Unit 7 whether Granola's plist is writing to the wrong path.
4. **Stale Ollama mentions in plan** — `Dependencies / Assumptions` section still references Ollama in two lines. Cosmetic; patch when Unit 4 is touched.
5. **Uncommitted changes** — Plan path rewrites and the Path Layout addition are not yet committed. Decision intentionally deferred to user.

### Execution order from here

```
Unit 1 (codex-delegate)  → venv + requirements.txt           ← NEXT
Unit 2 (codex-delegate)  → frontmatter.py + tests (TDD-first)
Unit 3 (codex-delegate)  → rules_classifier.py + tests
Unit 4 (codex-delegate)  → lm_classifier.py + tests (use tool_choice="required")
Unit 5 (codex-delegate)  → classify_vault.py CLI (Stage 0a pilot = Job Hunt folder)
Unit 6 (codex-delegate)  → export_granola.py R2 additions (granolaSync repo)
Unit 7 (claude)          → 11 MOC files + legacy up: rewriter (BLOCKED on Business Dataview install)
Unit 8 (claude)          → migrate_vault.py
```

### Where Unit 1 lands

| Thing | Path |
|---|---|
| Package | `evernote-to-obsidian/scripts/classify/__init__.py` |
| Requirements | `evernote-to-obsidian/scripts/classify/requirements.txt` (`openai>=1.30`, `PyYAML>=6.0`) |
| venv | `evernote-to-obsidian/scripts/classify/venv/` (gitignore) |
| Python entry path for all classifier commands | `evernote-to-obsidian/scripts/classify/venv/bin/python` |

Verification gate for Unit 1: `evernote-to-obsidian/scripts/classify/venv/bin/python -c "import openai, yaml; print('ok')"` exits 0.

### Environment gotchas (unchanged)

- Python 3.14 Homebrew, pip blocked system-wide — venv required
- `pytest` is a Homebrew formula — use bare `pytest`, never `python3 -m pytest`
- iCloud Drive under `~/Documents/` — atomic writes + 50ms inter-file sleep during bulk classification
- LM Studio: must remain running for Unit 4 mocked tests aren't enough; live integration test in Unit 4 needs the server up
- `LM_STUDIO_MODEL = "google/gemma-4-e4b"` — exact string from `/v1/models`

---

## 2026-05-14 AEST — Pre-flight + plan structure setup (superseded by entry above)

**Runner for next turn:** Claude (Unit 0 + 0.5 are claude-tagged in the plan).

**TL;DR for a fresh session:**
You are implementing the Obsidian universal knowledge graph plan. All planning, brainstorming, MOC design, schema decisions, and visualisation work is DONE. No implementation code has been written yet. The very next step is Unit 0 — verify Gemma 4 E4B in LM Studio responds to function-calling requests.

### Read these first (in order)

1. **`docs/plans/2026-05-13-001-feat-obsidian-knowledge-graph-beta-plan.md`** — the implementation plan. 9 units. Each unit has an `Execution target:` (claude or codex-delegate). Read the Routing Summary and the unit you're about to execute.
2. **`docs/brainstorms/2026-05-13-obsidian-knowledge-graph-requirements.md`** — the requirements doc. Read if the plan references a requirement (R1–R15) you need context on.
3. **`docs/diagrams/knowledge-graph-plan.html`** — visual walkthrough. Useful for orientation; not required.

### Pre-flight checks (do BEFORE Unit 0)

- [ ] **LM Studio installed and Gemma 4 E4B downloaded.** User confirmed download started 2026-05-14 but did not confirm completion. Verify in LM Studio → Discover or My Models that `google/gemma-4-e4b` shows as downloaded.
- [ ] **Load Gemma 4 E4B in LM Studio's Local Server tab.** Note the exact model identifier string LM Studio shows — this becomes `LM_STUDIO_MODEL` in Unit 4. Start the server (default port 1234).
- [ ] **Verify `~/Documents/ObsidianVault/Personal/` and `~/Documents/ObsidianVault/Business/` both exist.** Plan assumes both.
- [ ] **Verify Personal vault's Dataview plugin is installed.** Business vault Dataview: user confirmed it's installed too.
- [ ] **Confirm the existing `Personal/Meetings Homepage.md` and ~9 Granola notes with `up: "[[Meetings Homepage]]"` are present.** These will be renamed by the legacy rewriter in Unit 7.

### Unresolved structural question — surface to user BEFORE Unit 1

The plan as written has all new classifier code landing in `granolaSync/classify/` while extending `evernote-to-obsidian/scripts/classify_notes.py`. This creates an awkward cross-repo dependency. Two paths:

- **Option A (plan as-written):** Code in granolaSync, imports from evernote-to-obsidian. Means initialising granolaSync as its own git repo first (currently empty GitHub repo, no `.git` locally, same workspace-git issue as before).
- **Option B (recommended):** Move all new classifier code into `evernote-to-obsidian/scripts/classify/` — same repo as the existing `classify_notes.py` it extends. Only Unit 6 (Granola export schema changes) stays in granolaSync.

Ask the user before starting Unit 1.

### Execution order (from plan §Sequencing)

```
Unit 0 (claude)  → LM Studio verify
Unit 0.5 (claude) → Tarball backup of both vaults
Unit 1 (codex)   → venv + requirements.txt
Unit 2 (codex)   → frontmatter.py module + tests
Unit 3 (codex)   → rules_classifier.py (extends classify_notes.py)
Unit 4 (codex)   → lm_classifier.py (Gemma 4 E4B via OpenAI client)
Unit 5 (codex)   → classify_vault.py CLI (Stage 0a: Job Hunt folder pilot)
Unit 6 (codex)   → export_granola.py R2 schema additions
Unit 7 (claude)  → 11 MOC files in both vaults + legacy up: rewriter
Unit 8 (claude)  → migrate_vault.py (work notes → Business, personal → Personal flat)
```

### Critical decisions already locked

- **LLM:** Gemma 4 E4B (Q4_K_M, 6.33 GB) via LM Studio's OpenAI-compatible server (port 1234). NOT Ollama. NOT raw-prompt JSON — use function calling (tool use) for schema-enforced output.
- **Confidence threshold:** 0.80. Manually calibrated on 80 AWS filenames.
- **Pilot scope:** Job Hunt folder (~35 notes) FIRST. AWS folder (6,375 notes, ~15h LLM run) SECOND.
- **Schema fields:** type, org, context, people, tags, project, up, classify_confidence. 15 type values including interview, management, application, career, pattern. Tags include STAR markers and AWS leadership-principle tags.
- **MOC names are SHORT single words** where possible: `Meetings`, `Technical`, `Personal`, `People`, `Companies`, `Projects`, `Reference`, `Patterns`, `Leadership`. Two-word names only where clarity demands: `Interview Prep`, `Job Hunt`.
- **End state:** Zero `Evernote/` folders in either vault. All notes flat in vault root, organised by MOCs.

### Environment gotchas (read before running anything)

- **Python:** Homebrew Python 3.14. `pip install` is BLOCKED system-wide (PEP 668). Always use a venv.
- **`pytest`:** Use bare `pytest` command. Never `python3 -m pytest` (pytest is a Homebrew formula, not in Python site-packages).
- **iCloud Drive:** Both vaults are under `~/Documents/` which is iCloud-synced. Use atomic writes (`.tmp` + rename) and a 50ms sleep between file writes during bulk classification to avoid triggering sync storms.
- **macOS Full Disc Access:** The granolaSync LaunchAgent (`com.gilesparnell.granola-watcher.plist`) requires `/opt/homebrew/bin/python3` to have Full Disc Access to write to `~/Documents/ObsidianVault/`. Already granted but worth knowing.
- **Workspace-level `.git`:** `~/Documents/VSStudio/.git` exists (origin: resume-builder.git). This is a known mess. Inside `evernote-to-obsidian/` the local `.git` takes precedence. granolaSync still has the workspace-level git issue — needs its own `git init` before any Unit 1 work commits there.

### Where things live

| Thing | Path |
|---|---|
| Plan | `docs/plans/2026-05-13-001-feat-obsidian-knowledge-graph-beta-plan.md` |
| Brainstorm / requirements | `docs/brainstorms/2026-05-13-obsidian-knowledge-graph-requirements.md` |
| Visualisation | `docs/diagrams/knowledge-graph-plan.html` |
| Project hub | `docs/index.html` (live at <https://gilesparnell.github.io/evernote-to-obsidian/>) |
| Existing classifier | `scripts/classify_notes.py` (extend, don't rebuild) |
| Existing test suite | `tests/unit/test_classify_notes.py` |
| Personal vault | `~/Documents/ObsidianVault/Personal/` |
| Business vault | `~/Documents/ObsidianVault/Business/` |
| AWS source notes | `~/Documents/ObsidianVault/Personal/Evernote/notes/AWS/` (6,375 notes) |
| Job Hunt source notes | `~/Documents/ObsidianVault/Personal/Job Hunt/` (~35 notes — pilot scope) |
| granolaSync (where Unit 6 lands) | `/Users/gilesparnell/Documents/VSStudio/personal/granolaSync/` |
| Vault backup destination | `~/Backups/ObsidianVault-pre-classification-<YYYY-MM-DD>.tar.gz` |

### TDD posture

`tdd-first` is mandatory for every unit that produces code. Each unit in the plan specifies test file paths. Write the tests FIRST, confirm RED, then implement. Full test suite must be GREEN before declaring a unit done. The plan's `Verification:` line is the gate.

---

## 2026-05-14 AEST — Docs site live on GitHub Pages; repos initialised

**Runner:** Claude (infrastructure work)

**What changed:**
- `gilesparnell/evernote-to-obsidian` created on GitHub (PUBLIC).
- `gilesparnell/granolaSync` created on GitHub (PRIVATE, no content pushed yet).
- Plan, brainstorm, knowledge-graph-plan.html visualisation, handoff log moved from `granolaSync/docs/` to `evernote-to-obsidian/docs/`.
- New `evernote-to-obsidian/docs/index.html` project hub page (bento grid, Deep Ocean Tech design).
- `.gitignore` added to `evernote-to-obsidian/` — excludes all personal Evernote data, venvs, caches.
- Discovery: `~/Documents/VSStudio/` itself is a single workspace-level git repo (originally resume-builder). `evernote-to-obsidian/` and `granolaSync/` did NOT have their own `.git` directories before today. Resolved by `git init` in each project directory.
- Initial fresh-history commit pushed to `evernote-to-obsidian/main`.
- GitHub Pages enabled (serving `/docs` from `main`).
- Hub site card added at `gilesparnell.github.io/`.

**Live URLs:**
- Project hub: <https://gilesparnell.github.io/evernote-to-obsidian/>
- Visualisation: <https://gilesparnell.github.io/evernote-to-obsidian/diagrams/knowledge-graph-plan.html>
- Repo: <https://github.com/gilesparnell/evernote-to-obsidian>

**What's next:**
- Resume the implementation plan from Unit 0 (LM Studio Gemma 4 E4B verification). Plan lives at `docs/plans/2026-05-13-001-feat-obsidian-knowledge-graph-beta-plan.md`.
- granolaSync repo on GitHub is empty — needs its own `git init` + push when ready. Per user instruction, not done today.
- Workspace-level git at `~/Documents/VSStudio/.git` (origin: resume-builder.git) was untouched after recovery; that's a separate cleanup.

**Gotchas:**
- `~/Documents/VSStudio/.git` exists at workspace level. Inside subdirectories with their own `.git` (now: evernote-to-obsidian; later: granolaSync once initialised), the inner `.git` wins. Outside those subtrees the workspace git is what's seen.
- The 4.7 GB `evernote-migration/en_backup.db` and ~3.4 GB of `.enex` exports are gitignored — verify gitignore is intact before any future `git add`.

---

## 2026-05-14 AEST — Plan updated: Gemma 4 E4B, MOCs, flat vault structure, ready to execute Unit 0

**Runner:** Claude → Codex (plan written; execution starts with Unit 0)

**What was completed:**
- Full brainstorm + requirements doc: `docs/brainstorms/2026-05-13-obsidian-knowledge-graph-requirements.md`
- Implementation plan: `docs/plans/2026-05-13-001-feat-obsidian-knowledge-graph-beta-plan.md`
- Plan iteratively refined to incorporate: Gemma 4 E4B via LM Studio (OpenAI-compatible + function calling); MOCs (Maps of Content) instead of hub pages, with Nick Milo inbox pattern; flat vault structure with zero Evernote folders as end state; `classify_confidence` field in frontmatter; Job Hunt folder as pilot before AWS; Markdown review queue.
- Plan adds five interview-prep-specific MOCs and types: `Interview Prep` (type: interview), `Leadership` (type: management), `Job Hunt` (type: application), `Career` (type: career), `Patterns` (type: pattern).
- Plan adds Obsidian tag inference for STAR / AWS LP / quality tags via classifier and LM Studio function-calling schema.
- Plan adds Unit 0.5 (vault tarball backup) before any writes; legacy `up: [[Meetings Homepage]]` → `[[Meetings]]` rewriter; live LM Studio smoke test for Unit 4; MOC inbox query smoke test for Unit 7; throughput estimate (~15 hours for AWS pilot).
- Confidence threshold calibrated at 0.80 via manual analysis of 80 AWS filenames.
- All prior granolaSync work (Meetings Homepage rename, empty-note skip gate, up: link fix, plist WatchPaths refactor) complete; 58 tests passing.

**Current state:**
- Ollama is installed (`/opt/homebrew/bin/ollama`) but **no models pulled, daemon not running**
- Python 3.14 Homebrew — pip is blocked system-wide; use venv at `granolaSync/classify/venv/`
- `pytest` invoked as bare command (Homebrew formula, not in Python site-packages)
- Dataview v0.5.68 in Personal vault only; Business vault has no Dataview

**What's next:**
- **Unit 0 (claude):** Wait for Gemma 4 E4B download in LM Studio, load in Local Server tab, run curl smoke test against `http://localhost:1234/v1` to verify function calling.
- **Unit 0.5 (claude):** Tarball backup of both vaults to `~/Backups/ObsidianVault-pre-classification-<DATE>.tar.gz`.
- **Unit 1 (codex-delegate):** Create `granolaSync/classify/` package with venv + requirements.txt.
- Then Units 2–6 in sequence (all codex-delegate).

**Gotchas for next session:**
- Do NOT use `python3 -m pytest` — use bare `pytest`
- Do NOT use bare `pip install` — always via venv: `granolaSync/classify/venv/bin/pip install`
- iCloud sync risk: bulk writes to `~/Documents/ObsidianVault/` must use atomic writes + 50ms sleep between notes
- `evernote-to-obsidian/scripts/classify_notes.py` exists — **extend it, do not rebuild**
- LM Studio: use OpenAI-compatible client at `http://localhost:1234/v1`; use function calling (tool use) not raw JSON prompt
- MOC note names are SHORT: `Meetings`, `Technical`, `Personal`, `People`, `Companies`, `Projects`, `Reference` — NOT "Meetings Homepage" etc.
- `UP_MAP` uses these short names; existing `Meetings Homepage.md` in Personal vault will be renamed to `Meetings.md` in Unit 7
- End state: zero `Evernote/` folders in either vault; all notes flat in vault root
- Business vault path: `~/Documents/ObsidianVault/Business/`
- Personal vault path: `~/Documents/ObsidianVault/Personal/`
