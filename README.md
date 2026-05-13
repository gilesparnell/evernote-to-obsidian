# evernote-to-obsidian

One-shot batch tooling for migrating an Evernote export into a structured Obsidian knowledge graph.

## What this does

1. **Migrates Evernote** — extracts notes from `.enex` format, converts to Obsidian markdown (predates the May 2026 classifier work).
2. **Classifies notes** — rules-first → LM Studio fallback (Gemma 4 E4B) cascade emitting the R2 schema: `type`, `org`, `context`, `people`, `tags`, `classify_confidence`.
3. **Builds MOCs** — 16 Maps of Content across two vaults using Nick Milo's Dataview inbox pattern.
4. **Migrates vault structure** — moves classified notes out of `Evernote/` subfolders into the right vault (work → Business, personal → Personal), flat root.

See `docs/plans/2026-05-13-001-feat-obsidian-knowledge-graph-beta-plan.md` for the full architecture and the 9-unit implementation plan.

## What's in here

| Path | Purpose |
|---|---|
| `evernote-migration/` | Original `.enex` → `.md` conversion via Yarle |
| `scripts/classify_notes.py` | Original Work/Personal binary classifier (foundation) |
| `scripts/classify/` | R2 classifier package (Units 1–8 of the plan) |
| ↳ `frontmatter.py` | Atomic R2 frontmatter read/write |
| ↳ `rules_classifier.py` | Keyword scoring, 4 orgs × 10 types × 34 tags |
| ↳ `lm_classifier.py` | Gemma 4 E4B via LM Studio function calling |
| ↳ `classify_vault.py` | Batch pipeline CLI |
| ↳ `migrate_legacy_up.py` | One-shot legacy `up:` rewriter |
| ↳ `migrate_vault.py` | Move classified notes out of `Evernote/` subfolders |
| `tests/unit/`, `tests/integration/` | 163 pytest tests |
| `docs/plans/`, `docs/handoff/`, `docs/decisions/` | Plan, handover, tactical decisions |
| `docs/index.html`, `docs/status-2026-05-14.html` | GitHub Pages site |

## Quick start

Requires:
- Python 3.14 (Homebrew). `pip` is PEP 668-blocked system-wide — venv mandatory.
- LM Studio with `google/gemma-4-e4b` loaded on port 1234 (for the LM fallback path).

```bash
# venv
python3 -m venv scripts/classify/venv
scripts/classify/venv/bin/pip install -r scripts/classify/requirements.txt

# Test suite (163 tests + 3 live deselected)
scripts/classify/venv/bin/pytest -q

# Live LM Studio smoke tests (requires running server)
scripts/classify/venv/bin/pytest -m integration_live -v

# Classify a folder (Stage 0a pilot: Job Hunt, ~35 notes)
scripts/classify/venv/bin/python scripts/classify/classify_vault.py \
  --vault ~/Documents/ObsidianVault/Personal \
  --folder "Job Hunt"
```

Project conventions live in `CLAUDE.md`.

## Related repo

[`granolaSync`](https://github.com/gilesparnell/granolaSync) — the upstream daemon that pulls new Granola meeting notes into Obsidian daily, pre-classified with the same R2 schema. Both repos share canonical org names (`Amazon`, `T-Systems`, `TSC`, `Parnell Systems`) and the MOC names — if you change either, update both.

## Status

All 9 plan units shipped on 2026-05-14. The classifier hasn't been run against the real vault yet — the next operational step is the Job Hunt pilot. See `docs/status-2026-05-14.html` for the full state breakdown.

## Licence

Personal project. No licence granted.
