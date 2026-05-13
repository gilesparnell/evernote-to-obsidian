# Handoff Log

Newest entry at top. Each entry is a resumable snapshot for a fresh Claude or Codex session.

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
