# Project Conventions — evernote-to-obsidian

This file is read by Claude Code on every session. Keep it tight; defer detail to `docs/`.

## Test runner

Use the project venv's pytest. Bare Homebrew `pytest` cannot see PyYAML (its libexec Python is locked, no pip).

```bash
scripts/classify/venv/bin/pytest -q                            # full suite, live tests skipped
scripts/classify/venv/bin/pytest tests/unit/classify -v        # classifier unit tests
scripts/classify/venv/bin/pytest -m integration_live           # hit running LM Studio
```

## Python environment

Homebrew Python 3.14. `pip` is PEP 668-blocked system-wide. Always use the venv at `scripts/classify/venv/`. Never run bare `pip install` against system Python.

## Vault paths

- Personal vault: `~/Documents/ObsidianVault/Personal/`
- Business vault: `~/Documents/ObsidianVault/Business/`

Both are iCloud Drive-synced. Bulk writes MUST use atomic `.tmp` + rename (see `scripts/classify/frontmatter.py`'s `write_frontmatter`). The batch pipeline already inserts a 50 ms sleep between writes.

## LM Studio

- Endpoint: `http://localhost:1234/v1`
- Model identifier: `google/gemma-4-e4b`
- API key (placeholder): `"lm-studio"` — the server ignores it but the OpenAI SDK requires non-empty
- `tool_choice="required"` (string form only — the OpenAI object form returns HTTP 400 in LM Studio's compat server)

Live integration tests are marked `@pytest.mark.integration_live` and skipped by default via `pyproject.toml` `addopts = ["-m", "not integration_live"]`.

## Plan-driven workflow

Plans live in `docs/plans/`. Handover state in `docs/handoff/handoff.md` (newest entry at top). Tactical decisions in `docs/decisions/decisions.md`. **Update the handoff entry when finishing any plan unit** — that's how a fresh session resumes mid-flight.

## Related repo

[`granolaSync`](https://github.com/gilesparnell/granolaSync) is the upstream daemon producing new Granola meeting notes. The R2 schema's canonical names live HERE:

- `scripts/classify/rules_classifier.py` → `ORG_KEYWORDS` keys (canonical org names)
- `scripts/classify/classify_vault.py` → `UP_MAP` (canonical MOC names)

If you add a new org or rename a MOC, update granolaSync's `export_granola.py` to match — its `ORG_DOMAINS` map and the hardcoded `up:` string need to agree with this repo.

## Gotchas

- Workspace-level `.git` at `~/Documents/VSStudio/.git` (origin: resume-builder.git) is a separate concern. Inside this directory the local `.git` wins, but `cd ..` and `git` is back on the workspace repo.
- The `evernote-migration/en_backup.db` (4.7 GB) and `.enex` exports are gitignored — verify before any future `git add`.
- The `tdd-first` and `verification-before-completion` skills are always-active globally. Any logic-bearing change needs failing tests first; nothing is claimed done until tests are green and shown.
