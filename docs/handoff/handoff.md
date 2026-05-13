# Handoff Log

Newest entry at top. Each entry is a resumable snapshot for a fresh Claude or Codex session.

---

## 2026-05-14 AEST — ▶ RESUME HERE: ALL 9 plan units done — pilot is the next operational step

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

1. **Smoke-test the MOC inbox pattern in Obsidian.** Open `Personal/Meetings.md`, create a throwaway note with `up: "[[Meetings]]"`, confirm it appears in the Dataview LIST within ~2s. Repeat for `Job Hunt.md` and `Interview Prep.md`.
2. **Install Dataview in the Business vault.** Pre-flight showed it's missing. Business MOCs' Dataview queries render as plain code blocks until installed.
3. **Stage 0a pilot — classify the Job Hunt folder (~35 notes).** Run:
   ```
   scripts/classify/venv/bin/python scripts/classify/classify_vault.py \
     --vault ~/Documents/ObsidianVault/Personal \
     --folder "Job Hunt"
   ```
   Review `~/Documents/ObsidianVault/Personal/classification-review.md` for accuracy.
4. **Stage 0b — classify Evernote/notes/AWS** (6,375 notes, ~15h LLM inference). Run overnight or chunked with `--limit 500`.
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
