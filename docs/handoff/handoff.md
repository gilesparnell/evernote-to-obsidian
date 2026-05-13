# Handoff Log

Newest entry at top. Each entry is a resumable snapshot for a fresh Claude or Codex session.

---

## 2026-05-14 AEST — ▶ RESUME HERE: ready to start Unit 0 of the knowledge-graph plan

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
