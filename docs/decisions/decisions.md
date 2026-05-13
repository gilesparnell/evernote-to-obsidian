# Decisions Log

Project-local tactical decisions made during plan execution. Newest at top. Promote to a cross-project ADR only when impact extends outside this project.

---

## 2026-05-14 AEST — Units 4–8 executed by Claude despite codex-delegate tags

Plan tagged Units 4, 5, 6 as `codex-delegate`. Two attempted Codex round-trips (Unit 3 + Unit 4) both reported done but produced no files on disc — every expected path was missing across the entire user filesystem. Without seeing Codex's actual session output, the failure mode couldn't be diagnosed. User explicitly chose to keep work in Claude for the remainder of the plan. Recording the override so future planning doesn't keep routing units to a tool that's not functioning in this setup. Codex routing should be re-evaluated only after the underlying issue is found (sandbox? wrong working directory? plan mode?). See handoff log 2026-05-14 entries.

## 2026-05-14 AEST — Run classify tests via venv pytest, not bare pytest

Bare `pytest` (Homebrew formula at `/opt/homebrew/bin/pytest`) uses a locked libexec Python with no `pip` binary, so PyYAML can't be installed into it. The classify package depends on PyYAML, so its tests can't run under bare pytest. Resolution: `pytest>=8.0` added to `scripts/classify/requirements.txt`, and classify tests are invoked via `scripts/classify/venv/bin/pytest`. This venv-pytest also runs the existing 102 tests cleanly (they have no extra dependencies), so it is now the single command for the whole suite. Bare `pytest` still works for the existing tests but will skip-collect the classify tests with a yaml ImportError. Plan §Unit 2 verification gate updated.

## 2026-05-14 AEST — LM Studio `tool_choice` requires string form, not object

LM Studio's OpenAI-compatible chat-completions endpoint rejects the object-form `tool_choice={"type":"function","function":{"name":"..."}}` with HTTP 400 (`Invalid tool_choice type: 'object'`). Only string values `none`/`auto`/`required` are accepted. Verified during Unit 0 smoke test against `google/gemma-4-e4b`. Implementation impact: Unit 4 (`lm_classifier.py`) must call the OpenAI SDK with `tool_choice="required"`. With a single tool exposed, this is functionally identical to forcing the named function. See `docs/plans/2026-05-13-001-feat-obsidian-knowledge-graph-beta-plan.md` §Unit 4 (updated 2026-05-14).

## 2026-05-14 AEST — Classifier code lives in `evernote-to-obsidian/`, not granolaSync

Option B chosen over the original plan layout (which placed new classifier code in `granolaSync/classify/`). Reason: the new code *extends* `evernote-to-obsidian/scripts/classify_notes.py`, and splitting it across repos creates a cross-repo import dependency and a second `git init` overhead. Only Unit 6 (Granola export schema additions) stays in granolaSync because it modifies `export_granola.py` which lives there. Plan doc was path-rewritten and a `## Path Layout` section added. See plan §Path Layout.
