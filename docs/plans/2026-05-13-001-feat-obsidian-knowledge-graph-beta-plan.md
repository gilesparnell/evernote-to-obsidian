---
date: 2026-05-13
type: feat
title: "feat: Obsidian universal knowledge graph — classification pipeline + MOCs"
origin: docs/brainstorms/2026-05-13-obsidian-knowledge-graph-requirements.md
---

# feat: Obsidian Knowledge Graph — Classification Pipeline + MOCs

## Routing Summary

| Runner | Units | Total |
|--------|-------|-------|
| codex-delegate | 1, 2, 3, 4, 5, 6 | 6 |
| claude | 0, 0.5, 7, 8 | 4 |

**claude units:**
- **Unit 0** — LM Studio verification requires interactive shell commands and JSON compliance testing against a live local server.
- **Unit 0.5** — Vault backup is a one-shot destructive-mitigation step; needs careful manual verification that the tarball is valid before any writes happen.
- **Unit 7** — MOC design requires semantic decisions (inbox query structure, grouping axes, which MOCs go in which vault) that are architectural, not mechanical.
- **Unit 8** — Vault migration tooling moves 8,000+ files irreversibly; the design of the safety gates and batch confirmation flow is judgement-heavy.

---

## Problem Frame

10,000+ Obsidian notes across Personal and Business vaults have no consistent frontmatter schema. Evernote-imported notes are folder-contaminated (personal notes in the AWS work folder and vice versa). The goal is:

1. A universal frontmatter schema (R1–R3, see origin doc)
2. A confidence-gated classification pipeline extending the existing `evernote-to-obsidian/scripts/classify_notes.py` (R4–R7)
3. Granola export updated to classify new notes at export time (R8)
4. Dataview-powered MOCs (Maps of Content) once classification coverage is sufficient (R12–R15)
5. Vault migration tooling as a separate explicit step (R9–R11)

Confidence threshold: **0.80** (calibrated against 80 AWS filenames — 66% auto-classify, 33% review queue).

---

## Source Document

Requirements doc: `docs/brainstorms/2026-05-13-obsidian-knowledge-graph-requirements.md`

Key decisions carried forward:
- Folder path = hint, not authority (content wins on conflict)
- Classification before MOCs
- Vault migration = separate explicit step
- 0.80 confidence threshold

---

## Architecture Overview

*Directional — not implementation specification. Implementer treats this as context, not code to reproduce.*

```
┌─────────────────────────────────────────────────────────────┐
│  classify_vault.py  (Unit 5 — batch pipeline CLI)           │
│  ┌─────────────────────────────────────────┐                │
│  │  1. glob all .md in vault               │                │
│  │  2. skip already-classified (has all    │                │
│  │     R2 fields present in frontmatter)   │                │
│  │  3. read body (strip existing FM)       │                │
│  │  4. rules_classifier.classify()  ───────┼──> ≥0.80 → write frontmatter
│  │     (Unit 3 — richer keyword scoring)   │       < 0.80 → review queue
│  │  5. if still uncertain → LM Studio pass │                │
│  │     (Unit 4 — Gemma 4 E4B tool calling) │                │
│  │  6. write checkpoint every 50 notes     │                │
│  └─────────────────────────────────────────┘                │
│                                                             │
│  review queue: classification-review.md (R6)                │
│  checkpoint:   .classify_checkpoint.json                    │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  frontmatter.py  (Unit 2 — read/write module)               │
│  read_frontmatter(path) → dict                              │
│  write_frontmatter(path, fields: dict)  (merge, not clobber)│
│  is_classified(path) → bool  (all R2 fields present)        │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  export_granola.py  (Unit 6 — new notes classified inline)  │
│  classify_granola_note(doc) → R2 field dict                 │
│  Uses meeting metadata: title, attendees, calendar event    │
└─────────────────────────────────────────────────────────────┘
```

---

## Codebase Context

**Extend, don't rebuild:**

| Existing file | What it has | What plan extends |
|---|---|---|
| `evernote-to-obsidian/scripts/classify_notes.py` | `score_note()`, `classify_with_rules()`, `classify_with_ollama()` | Extend rule keyword sets; add richer org/type/people signals; replace Ollama transport with LM Studio OpenAI-compatible client + function calling |
| `export_granola.py` | `build_frontmatter()`, attendee extraction | Add R2 fields using meeting metadata as classification signal |

**Vault paths:**
- Personal: `~/Documents/ObsidianVault/Personal/`
- Business: `~/Documents/ObsidianVault/Business/`

**Evernote note layout (Personal vault):**
```
Personal/Evernote/notes/AWS/       (6,375 notes — contaminated)
Personal/Evernote/notes/T-Systems/ (1,720 notes)
Personal/Evernote/notes/TSC/       (958 notes)
Personal/Evernote/notes/Personal NoteBook/ (1,414 notes)
Personal/Evernote/notes/Work - General/ (48 notes)
Personal/Evernote/notes/Cooking/   (40 notes)
```

---

## R2 Schema (carried from origin)

```yaml
type: meeting | note | technical | reference | person | company | project | recipe | journal | personal | interview | management | application | career | pattern
org: "Amazon" | "T-Systems" | "TSC" | "Parnell Systems" | "Personal" | <other>
context: work | personal | education
people: ["First Last", ...]
project: "Project Name"   # optional, omit if not applicable
tags: ["star", "weakness", "aws-lp/customer-obsession", ...]   # Obsidian native tags, classifier-inferred
up: "[[MOC Name]]"
```

**Tag taxonomy** (classifier-inferred where signals are present):
- **STAR / interview tags:** `star`, `weakness`, `failure-story`, `success-story`, `behavioral`, `technical-deep-dive`, `system-design`, `coding`
- **AWS leadership principles:** `aws-lp/customer-obsession`, `aws-lp/ownership`, `aws-lp/invent-simplify`, `aws-lp/are-right-a-lot`, `aws-lp/learn-and-be-curious`, `aws-lp/hire-and-develop`, `aws-lp/insist-on-highest-standards`, `aws-lp/think-big`, `aws-lp/bias-for-action`, `aws-lp/frugality`, `aws-lp/earn-trust`, `aws-lp/dive-deep`, `aws-lp/have-backbone`, `aws-lp/deliver-results`, `aws-lp/strive-to-be-earths-best-employer`, `aws-lp/success-and-scale`
- **Job hunt:** `applied`, `interviewing`, `offer`, `rejected`, `withdrawn`
- **Quality:** `polished`, `draft`, `needs-review`

Tags are additive — a STAR story about customer escalation might carry `["star", "aws-lp/customer-obsession", "polished"]`.

`up` values by type (links each note to its parent MOC):
- `type: meeting` → `[[Meetings]]`
- `type: technical` → `[[Technical]]`
- `type: reference` → `[[Reference]]`
- `type: person` → `[[People]]`
- `type: company` → `[[Companies]]`
- `type: recipe` → `[[Personal]]`
- `type: journal | personal | note` → `[[Personal]]`
- `type: project` → `[[Projects]]`
- `type: interview` → `[[Interview Prep]]`
- `type: management` → `[[Leadership]]`
- `type: application` → `[[Job Hunt]]`
- `type: career` → `[[Career]]`
- `type: pattern` → `[[Patterns]]`

MOC note names are short where possible — they're the radial centres in graph view, not document titles. Two-word names (`Interview Prep`, `Job Hunt`) are used where single-word alternatives lose clarity.

---

## Implementation Units

---

### Unit 0: LM Studio Environment Verification

**Execution target: claude**
**Goal:** Verify Gemma 4 E4B is loaded in LM Studio's local server and returning valid structured JSON via function calling before any classifier code is written.

**Model:** `google/gemma-4-e4b-it` (Gemma 4 E4B Instruct, Q4_K_M, 6.33 GB). 16 GB RAM — full GPU offload possible.

**Requirements:** Prerequisite for Units 3–5.

**Dependencies:** None. LM Studio already installed and Gemma 4 E4B downloaded.

**Files:** None created in this unit.

**Approach:**

1. Open LM Studio → **Local Server** tab → load `Gemma 4 E4B Instruct` → click **Start Server**
2. Note the model identifier shown in the server (e.g. `gemma-4-e4b-instruct`) — this becomes `LM_STUDIO_MODEL` in Unit 4
3. Run a JSON compliance test via curl to confirm function calling works before writing any Python:
   ```bash
   curl -s http://localhost:1234/v1/chat/completions \
     -H "Content-Type: application/json" \
     -d '{
       "model": "<model-id-from-lm-studio>",
       "messages": [{"role": "user", "content": "Classify this note title: Weekly AWS standup"}],
       "tools": [{
         "type": "function",
         "function": {
           "name": "classify_note",
           "parameters": {
             "type": "object",
             "properties": {
               "type": {"type": "string"},
               "org": {"type": "string"},
               "context": {"type": "string"},
               "confidence": {"type": "number"}
             },
             "required": ["type", "org", "context", "confidence"]
           }
         }
       }],
       "tool_choice": {"type": "function", "function": {"name": "classify_note"}}
     }' | python3 -m json.tool
   ```
4. Confirm the response contains `tool_calls[0].function.arguments` with valid JSON

**Verification:**
- LM Studio server shows "Running" status
- curl test returns parseable JSON with `type`, `org`, `context`, `confidence` fields
- `confidence` value is a float, not a string

---

### Unit 0.5: Vault Backup (Safety Net)

**Execution target: claude**
**Goal:** Capture a recoverable snapshot of both vaults before any frontmatter writes happen. About to mutate 10,000+ files; iCloud Drive versioning is lossy and can't be trusted as the sole backup.

**Dependencies:** None.

**Files:** None created in repo. Backup written to `~/Backups/ObsidianVault-pre-classification-<YYYY-MM-DD>.tar.gz`.

**Approach:**

1. Confirm both vault paths exist:
   ```bash
   ls -d ~/Documents/ObsidianVault/Personal ~/Documents/ObsidianVault/Business
   ```
2. Create tarball with date stamp:
   ```bash
   mkdir -p ~/Backups
   tar -czf ~/Backups/ObsidianVault-pre-classification-$(date +%Y-%m-%d).tar.gz \
     -C ~/Documents ObsidianVault
   ```
3. Verify the tarball is non-empty and readable:
   ```bash
   ls -lh ~/Backups/ObsidianVault-pre-classification-*.tar.gz
   tar -tzf ~/Backups/ObsidianVault-pre-classification-*.tar.gz | head
   ```
4. Document the backup path in `docs/handoff/handoff.md` so any future restore is one command away.

**Restore procedure (for the runbook):**
```bash
mv ~/Documents/ObsidianVault ~/Documents/ObsidianVault.broken
tar -xzf ~/Backups/ObsidianVault-pre-classification-<DATE>.tar.gz -C ~/Documents/
```

**Verification:**
- Tarball exists and is >100MB (sanity check that both vaults captured)
- `tar -tzf` lists files from both `Personal/` and `Business/`
- Backup path logged in handoff

---

### Unit 1: Project Virtualenv + Dependencies

**Execution target: codex-delegate**
**Goal:** Create a project-local venv with all classifier dependencies.

**Requirements:** R4 (pipeline needs `ollama` package).

**Dependencies:** Unit 0 (Ollama daemon running, model pulled).

**Files:**
- `granolaSync/classify/requirements.txt` — new
- `granolaSync/classify/__init__.py` — new (empty)
- `granolaSync/classify/venv/` — created by setup, gitignored

**Approach:**
- `requirements.txt` contents: `openai>=1.30`, `PyYAML>=6.0`
- Setup command: `python3 -m venv granolaSync/classify/venv && granolaSync/classify/venv/bin/pip install -r granolaSync/classify/requirements.txt`
- Add `granolaSync/classify/venv/` to `.gitignore`
- The venv Python path for all classifier commands: `granolaSync/classify/venv/bin/python`
- LM Studio base URL: `http://localhost:1234/v1` (default; no API key required — pass `"lm-studio"` as placeholder)

**Patterns to follow:** Existing project has no venv — this is the first. Follow Homebrew Python 3.14 restriction (never use bare `pip install`).

**Test scenarios:** None (infrastructure only — verified by `openai` import succeeding in Unit 4).

**Verification:** `granolaSync/classify/venv/bin/python -c "import openai, yaml; print('ok')"` exits 0.

---

### Unit 2: Frontmatter Read/Write Module

**Execution target: codex-delegate**
**Goal:** A safe, idempotent module that reads existing frontmatter and merges new R2 fields without clobbering existing fields.

**Requirements:** R1 (existing fields preserved), R7 (already-classified notes skipped).

**Dependencies:** Unit 1 (venv with PyYAML).

**Files:**
- `granolaSync/classify/frontmatter.py` — new
- `granolaSync/tests/unit/classify/test_frontmatter.py` — new

**Approach:**

Three public functions:

```
read_frontmatter(path: Path) -> dict
    Parse YAML frontmatter block (between first --- and second ---).
    Return {} if no frontmatter present.
    Preserve existing values — do not interpret or transform them.

write_frontmatter(path: Path, new_fields: dict) -> None
    Read existing frontmatter.
    Merge new_fields into it (new_fields wins on key collision).
    Serialise back with yaml.dump, preserving field order:
      title, date → existing fields → R2 fields (type, org, context, people, project, up).
    Write atomically: write to .tmp file, then rename.

is_classified(path: Path) -> bool
    Return True iff frontmatter contains all required R2 fields:
    type, org, context, up.
    people and project are optional — do not require them for is_classified.
```

Atomic write pattern: `path.write_text` is NOT atomic on macOS. Write to `path.with_suffix('.tmp')`, then `path.with_suffix('.tmp').rename(path)`. This avoids partial writes if interrupted during iCloud sync.

**Patterns to follow:** `evernote-to-obsidian/scripts/classify_notes.py` `_FRONTMATTER_RE` pattern for regex frontmatter extraction.

**Test scenarios:**
- `read_frontmatter` on a note with no frontmatter → `{}`
- `read_frontmatter` on a note with existing `title`, `date`, `granola_id` → returns those fields
- `write_frontmatter` merges new fields without touching existing ones
- `write_frontmatter` on a note with no frontmatter creates a valid `---` block
- `is_classified` returns `False` when `type` is missing
- `is_classified` returns `True` when `type`, `org`, `context`, `up` all present
- `is_classified` returns `True` even when `people` and `project` are absent
- Atomic write: verify `.tmp` file does not persist after `write_frontmatter` returns

**Verification:** `pytest granolaSync/tests/unit/classify/test_frontmatter.py -v` — all pass.

---

### Unit 3: Extended Rules Classifier

**Execution target: codex-delegate**
**Goal:** Extend the existing `classify_with_rules()` to produce all R2 fields (type, org, context, people) from note content and filename, not just Work/Personal.

**Requirements:** R4 (content primary, folder secondary), R5 (returns confidence 0–1).

**Dependencies:** Unit 2.

**Files:**
- `granolaSync/classify/rules_classifier.py` — new (wraps + extends `evernote-to-obsidian/scripts/classify_notes.py`)
- `granolaSync/tests/unit/classify/test_rules_classifier.py` — new

**Approach:**

Do NOT modify `evernote-to-obsidian/scripts/classify_notes.py` directly — import from it and extend.

New keyword dictionaries (add to existing WORK/PERSONAL sets):

```python
ORG_KEYWORDS = {
    "Amazon": ["aws", "amazon", "s3", "ec2", "lambda", "cloudwatch", "redshift",
               "iam", "sagemaker", "kindle", "alexa"],
    "T-Systems": ["t-systems", "tsystems", "telekom", "magenta", "deutsche telekom"],
    "TSC": ["tsc", "transport systems", "catapult"],
    "Parnell Systems": ["parnell systems", "allconvos", "voice ai", "granola"],
}

TYPE_KEYWORDS = {
    "meeting": ["meeting", "standup", "stand-up", "retrospective", "1-1", "one-on-one",
                "agenda", "action items", "attendees", "minutes"],
    "technical": ["architecture", "design doc", "rfc", "api", "schema", "database",
                  "implementation", "algorithm", "code review", "pull request", "deployment"],
    "reference": ["reference", "cheatsheet", "cheat sheet", "how to", "howto",
                  "documentation", "notes on", "summary of", "overview"],
    "recipe": ["recipe", "ingredients", "cook", "cooking", "bake", "baking",
               "tablespoon", "teaspoon", "oven", "prep time"],
    "journal": ["today i", "feeling", "reflection", "diary", "personal note"],
    "interview": ["star", "situation task action result", "tell me about a time",
                  "interview question", "interview prep", "competency", "leadership principle",
                  "behavioural question", "behavioral question", "example of when",
                  "demonstrate", "accomplishment", "strength", "weakness"],
    "management": ["olr", "performance review", "performance management", "pip",
                   "direct report", "manager feedback", "calibration", "promotion",
                   "talent review", "coaching session", "career development",
                   "management practice", "leadership practice", "team health",
                   "low performer", "high performer", "succession"],
    "application": ["applied to", "job application", "role description",
                    "hiring manager", "recruiter", "screening call", "phone screen",
                    "onsite", "offer", "rejected", "withdrew application",
                    "interview stage", "applied via", "linkedin easy apply"],
    "career": ["cv", "resume", "achievements", "certification", "qualification",
               "professional summary", "career timeline", "linkedin profile",
               "education", "degree", "certified", "credentials"],
    "pattern": ["design pattern", "architectural pattern", "cqrs", "event sourcing",
                "saga pattern", "circuit breaker", "bulkhead", "cap theorem",
                "consistent hashing", "load balancing", "rate limiting",
                "service mesh", "domain driven", "ddd", "hexagonal", "clean architecture"],
}

TAG_PATTERNS = {
    "star": ["star story", "situation:", "task:", "action:", "result:"],
    "weakness": ["weakness", "area for improvement", "where i struggled"],
    "failure-story": ["failed", "didn't work", "post-mortem", "incident report"],
    "system-design": ["system design", "architecture review", "design doc"],
    "aws-lp/customer-obsession": ["customer obsession", "customer first", "customer escalation"],
    "aws-lp/ownership": ["ownership", "own the outcome", "above and beyond"],
    "aws-lp/dive-deep": ["dive deep", "root cause", "investigation"],
    "aws-lp/deliver-results": ["delivered", "shipped", "meeting deadlines"],
    "aws-lp/have-backbone": ["disagreed", "pushed back", "challenged"],
    # ...remaining AWS LP tags follow the same pattern
    "polished": ["[polished]", "tag: polished"],
    "draft": ["[draft]", "tag: draft", "wip", "work in progress"],
}

PEOPLE_PATTERN = re.compile(
    r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b"
)
```

`classify(title: str, body: str, folder_hint: str) -> dict`:
- Returns `{"type", "org", "context", "people", "tags", "confidence", "reason"}`
- `folder_hint` is the Evernote folder name (e.g. `"AWS"`) — used to break ties only, not to override content
- Org detection: score each org by keyword hits; pick highest if score > 0, else `"Personal"`
- Type detection: score each type by keyword hits; pick highest; fallback to `"note"`
- Context derived from org: Amazon/T-Systems/TSC → `"work"`, Parnell Systems → `"work"`, Personal → `"personal"`, else use work/personal keyword scores
- People: regex-extract capitalised name pairs from body, deduplicate, filter known false positives (Monday, Tuesday, January, etc.)
- Tags: scan body+title against `TAG_PATTERNS`; any match adds the tag. Empty list if no matches. The LM classifier (Unit 4) can also propose tags.
- Confidence: highest-scoring org proportion (0–1); minimum of org confidence and type confidence (tags don't affect confidence)

**Patterns to follow:** `evernote-to-obsidian/scripts/classify_notes.py` — `score_note()` pattern for keyword scoring.

**Test scenarios:**
- Note with "AWS S3 deployment meeting" → `org: Amazon`, `type: meeting`, `context: work`
- Note with "birthday party, family dinner, kids homework" → `org: Personal`, `type: personal`, `context: personal`
- Note with "recipe: chocolate cake, 2 cups flour" → `type: recipe`
- Note with "John Smith attended the standup with Alice Jones" → `people: ["John Smith", "Alice Jones"]`
- Note with no keywords, folder_hint `"AWS"` → org falls back to `"Amazon"` with low confidence
- Note with "AWS" keyword in body AND personal keywords → org=Amazon wins, context=work
- `"Tuesday Meeting"` as body → people list does NOT contain `"Tuesday"`
- Note with "STAR story, situation: customer escalation, action: escalated to VP" → `type: interview`, `tags: ["star", "aws-lp/customer-obsession"]`
- Note with "OLR calibration, direct report performance review, low performer" → `type: management`
- Note with "applied to Anthropic, phone screen scheduled Mar 14" → `type: application`
- Note with "CQRS pattern for write-heavy systems, event sourcing trade-offs" → `type: pattern`
- Note with "Resume summary: 15 years SRE leadership" → `type: career`
- Note with "[draft] STAR story about scaling team" → `tags` contains both `"star"` AND `"draft"`

**Verification:** `pytest granolaSync/tests/unit/classify/test_rules_classifier.py -v` — all pass.

---

### Unit 4: LM Studio Classifier (Gemma 4 E4B via Function Calling)

**Execution target: codex-delegate**
**Goal:** LM Studio classifier using Gemma 4 E4B's tool calling to emit guaranteed structured R2 JSON. Used only when rules confidence < 0.80.

**Requirements:** R4 (LM Studio as fallback for uncertain notes), R5 (confidence scoring).

**Dependencies:** Units 0 (LM Studio server verified), 1 (venv with `openai` package), 3 (rules classifier for fallback).

**Files:**
- `granolaSync/classify/lm_classifier.py` — new
- `granolaSync/tests/unit/classify/test_lm_classifier.py` — new

**Approach:**

Use OpenAI-compatible function calling to get guaranteed structured output — no prompt-based JSON parsing, no fence stripping:

```python
LM_STUDIO_BASE_URL = "http://localhost:1234/v1"
LM_STUDIO_MODEL = "gemma-4-e4b-instruct"   # exact string from LM Studio server tab

CLASSIFY_SCHEMA = {
    "name": "classify_note",
    "parameters": {
        "type": "object",
        "properties": {
            "type": {"type": "string", "enum": ["meeting","note","technical","reference",
                     "person","company","project","recipe","journal","personal",
                     "interview","management","application","career","pattern"]},
            "org":  {"type": "string", "enum": ["Amazon","T-Systems","TSC",
                     "Parnell Systems","Personal","Unknown"]},
            "context":    {"type": "string", "enum": ["work","personal","education","unknown"]},
            "people":     {"type": "array", "items": {"type": "string"}},
            "tags":       {"type": "array", "items": {"type": "string"}},
            "confidence": {"type": "number"},
            "reason":     {"type": "string"},
        },
        "required": ["type", "org", "context", "people", "tags", "confidence"],
    },
}
```

`classify(title: str, body: str, folder_hint: str) -> dict`:
- Creates `openai.OpenAI(base_url=LM_STUDIO_BASE_URL, api_key="lm-studio")`
- Calls `client.chat.completions.create()` with `tools=[...]` and `tool_choice={"type":"function", "function":{"name":"classify_note"}}`
- Extracts `tool_calls[0].function.arguments` and `json.loads()` — schema enforcement means this always parses
- On any exception (server down, timeout): returns `{"confidence": 0.0, "reason": "lm-studio unavailable"}` — never raises
- Maps `"Unknown"` org to `"Personal"` if context is also unknown

**Test scenarios (mock `openai.OpenAI`):**
- Valid tool_call response → all R2 fields extracted correctly
- Server returns no `tool_calls` (fallback to text) → returns `confidence: 0.0` without raising
- `openai` client raises `ConnectionError` → returns `confidence: 0.0` without raising
- `people` not in response arguments → defaults to empty list
- `tags` not in response arguments → defaults to empty list
- `confidence` > 1.0 in response → clamp to 1.0

**Live smoke test** (separate file, only runs when LM Studio is reachable):
- `granolaSync/tests/integration/classify/test_lm_classifier_live.py` — uses `@pytest.mark.integration_live`, skipped by default. Hits real LM Studio with three test prompts (a clear meeting note, a clear STAR story, a low-signal note) and asserts the function-calling response is parseable and matches expected types. Run with `pytest -m integration_live`. Validates that Gemma 4 E4B is honouring the schema enforcement (vs hallucinating in text).

**Verification:** 
- `pytest granolaSync/tests/unit/classify/test_lm_classifier.py -v` — mocked tests pass
- `pytest -m integration_live granolaSync/tests/integration/classify/test_lm_classifier_live.py -v` — live test against running LM Studio passes (run once during Unit 0, then on schema changes)

---

### Unit 5: Batch Classification Pipeline

**Execution target: codex-delegate**
**Goal:** CLI that runs the full classification pipeline across a vault, writes frontmatter for high-confidence notes, and outputs the review queue.

**Requirements:** R4–R7 (full pipeline, confidence gate, review queue, re-runnable).

**Dependencies:** Units 2, 3, 4.

**Files:**
- `granolaSync/classify/classify_vault.py` — new
- `granolaSync/tests/integration/classify/test_classify_vault.py` — new

**Approach:**

CLI: `python granolaSync/classify/classify_vault.py --vault <path> [--folder <subfolder>] [--dry-run] [--limit N]`

`--folder`: restrict processing to a single subfolder (e.g. `Evernote/notes/AWS`). Pilot order:
1. **Stage 0a — `--folder "Job Hunt"`** (~35 notes, runs in minutes). Validates the new `interview`/`management`/`application`/`career` types and tag inference work correctly on a small sample where every note should classify clearly. Review the result before scaling.
2. **Stage 0b — `--folder Evernote/notes/AWS`** (6,375 notes). Scale and contamination test. **~15 hours of LLM inference** (66% rule-classified at <1s each, 33% LM-classified at ~26s each). Run overnight or use `--limit 500` per session for visible progress.
3. **Stages 0c+** — remaining Evernote folders.

```
for each .md file in vault (recursively, scoped to folder if --folder given):
    if is_classified(path): skip (R7)
    extract body (strip frontmatter)
    if body < 50 chars: add to review queue with reason "too short to classify"
    result = rules_classifier.classify(title, body, folder_hint)
    if result.confidence < 0.80:
        result = ollama_classifier.classify(title, body, folder_hint)
    if result.confidence >= 0.80:
        up_value = up_for_type(result.type)
        write_frontmatter(path, {type, org, context, people, tags, up, classify_confidence})
        auto_classified_count += 1
    else:
        review_queue.append({path, proposed, confidence, reason})
    if (i % 50 == 0): write checkpoint (JSON list of processed paths)
```

iCloud sync safety:
- Write checkpoint every 50 notes
- Default batch size is unlimited; `--limit N` processes only first N unclassified notes per run
- Emit `time.sleep(0.05)` between file writes to avoid triggering iCloud sync storm

Review queue output (`classification-review.md` in vault root):
```markdown
# Classification Review Queue
Generated: <date>
<N> notes need manual review.

| Note | Proposed type | Proposed org | Confidence | Reason |
|------|--------------|-------------|------------|--------|
| [[path/to/note]] | meeting | Amazon | 0.61 | short body, no org keywords |
```

`up_for_type(type: str) -> str`:
```python
UP_MAP = {
    "meeting":  "[[Meetings]]",
    "technical":"[[Technical]]",
    "reference":"[[Reference]]",
    "person":   "[[People]]",
    "company":  "[[Companies]]",
    "recipe":   "[[Personal]]",
    "journal":  "[[Personal]]",
    "personal": "[[Personal]]",
    "note":     "[[Personal]]",
    "project":  "[[Projects]]",
}
```

**Patterns to follow:** `evernote-to-obsidian/scripts/classify_notes.py` `classify_notebook()` loop structure.

**Test scenarios (integration — use `tmp_path` fixture with real .md files):**
- Note already classified → skipped, count incremented
- Note with high-confidence rules result → frontmatter written, review queue empty
- Note with low rules confidence and mocked LM Studio returning high confidence → frontmatter written
- Note with low confidence from both → appears in review queue, frontmatter NOT written
- `--dry-run` flag → no files written, review queue printed to stdout only
- Checkpoint file written every 50 notes
- Notes with body < 50 chars → review queue with "too short" reason
- Review queue is valid Markdown with correct table format

**Verification:** `pytest granolaSync/tests/integration/classify/test_classify_vault.py -v` — all pass.

---

### Unit 6: Granola Export — Inline Classification

**Execution target: codex-delegate**
**Goal:** When `export_granola.py` writes a new meeting note, populate the full R2 schema using meeting metadata (no body content needed — meeting notes are always `type: meeting`, org/people come from attendees).

**Requirements:** R8 (new Granola notes classified at export time).

**Dependencies:** Unit 2 (frontmatter write module for schema reference; the actual write is already done by `export_granola.py`).

**Files:**
- `export_granola.py` — modify `build_frontmatter()` function
- `granolaSync/tests/unit/test_export_granola.py` — extend existing test class

**Approach:**

Granola export already has:
```python
'up: "[[Meetings Homepage]]"'
'attendees: [...]'
```

Extend `build_frontmatter()` to also emit:
```yaml
type: meeting
org: "<detected from attendee domains or calendar account>"
context: work
people: ["First Last", ...]   # from existing attendees list
```

Org detection for Granola notes:
- If attendee emails contain `@amazon.com` → `"Amazon"`
- If attendee emails contain `@t-systems.com` → `"T-Systems"`
- Else: `"Personal"` (safe default; user can correct in review)

`people` field: extract from the existing `attendees` list. Use first + last name only; drop email addresses.

Do NOT change how the frontmatter is written to disc — `export_granola.py` already writes the YAML block directly. Just extend the strings produced by `build_frontmatter()`.

**Patterns to follow:** Existing `build_frontmatter()` in `export_granola.py`.

**Test scenarios:**
- Attendees with `@amazon.com` emails → `org: "Amazon"` in output
- Attendees with no domain match → `org: "Personal"`
- `people` field contains full names from attendees, not email addresses
- `type: meeting` always present regardless of attendee list
- `context: work` always present for Granola exports
- Existing fields (`title`, `date`, `granola_id`, `up`) still present in output

**Verification:** `pytest granolaSync/tests/unit/test_export_granola.py -v` — all 58+ pass.

---

### Unit 7: MOCs (Maps of Content)

**Execution target: claude**
**Goal:** Create MOC notes in both vaults. Each MOC uses the Dataview inbox pattern (pioneered by Nick Milo) so that newly classified notes automatically appear in the MOC as soon as they're linked via `up:`, and can be progressively organised into manual sections.

**Requirements:** R12–R15 (MOCs, per-company pages, People index).

**Dependencies:** Unit 5 (meaningful classification coverage before MOCs are useful).

**Note on `up:` vs `parent::`:** The obsidian.rocks article uses `parent:: [[MOC Name]]` (Dataview inline metadata syntax). We use `up:` (YAML frontmatter) because it's already established in the Granola export schema and is compatible with the Breadcrumbs plugin. Both work identically in Dataview queries. We keep `up:`.

**Files:**
- `Personal/Home.md` — new (top-level navigation MOC linking all other Personal MOCs)
- `Personal/Meetings.md` — update existing `Meetings Homepage.md`, rename to `Meetings.md`
- `Personal/Personal.md` — new
- `Personal/People.md` — new
- `Personal/Reference.md` — new
- `Business/Home.md` — new (top-level navigation MOC linking all other Business MOCs)
- `Business/Meetings.md` — new
- `Business/Technical.md` — new
- `Business/Companies.md` — new
- `Business/People.md` — new
- `Business/Projects.md` — new
- `Personal/Interview Prep.md` — new (STAR stories, potential questions, competency evidence)
- `Business/Leadership.md` — new (OLR notes, performance management, management best practices)
- `Personal/Job Hunt.md` — new (active application pipeline, role research, interview stages)
- `Personal/Career.md` — new (resume bullets, achievements timeline, certifications)
- `Business/Patterns.md` — new (architectural patterns, design knowledge, system-design interview prep)
- `granolaSync/moc_templates/` — stub templates committed to repo for reference

**Legacy migration step (runs once before MOCs go live):**
Existing Granola-exported notes already have `up: "[[Meetings Homepage]]"`. After renaming the MOC file to `Meetings.md`, those notes' `up` links will be broken. A one-shot rewriter:
```bash
# In Personal vault, rewrite stale up: links in-place
find ~/Documents/ObsidianVault/Personal -name '*.md' -exec \
  sed -i '' 's|up: "\[\[Meetings Homepage\]\]"|up: "[[Meetings]]"|g' {} +
```
This is documented but should be added as a small script: `granolaSync/classify/migrate_legacy_up.py` with the same find+sed logic, plus a `--dry-run` flag and a count of rewrites.

**MOC anatomy (same pattern for every MOC):**

Every MOC has three sections:

1. **Header** — one line describing what this MOC covers
2. **Inbox** — Dataview query that automatically surfaces notes linking to this MOC that haven't been manually placed yet:
   ```dataview
   LIST FROM [[]] AND !outgoing([[]])
   ```
   This is the self-maintaining inbox. A note appears here the moment `up: "[[Meetings]]"` is written to it. Once you manually link it in section 3, it disappears from the inbox automatically.

3. **Organised sections** — manually curated headers (e.g. `## 2026`, `## Amazon`, `## 1-on-1s`) with wikilinks. This grows over time as the user works through the inbox.

**Approach — Dataview is installed in both vaults; create all MOCs directly.**

**`Meetings.md`** (Personal + Business, same structure):
```markdown
# Meetings
All meeting notes. New classified notes appear in the inbox below automatically.

## Inbox
\`\`\`dataview
LIST FROM [[]] AND !outgoing([[]])
\`\`\`

## Organised
<!-- Move entries from inbox to here, grouped however you like -->
```

**`Personal.md`** (Personal vault only):
```markdown
# Personal
Personal notes, journals, recipes, and anything context: personal.

## Inbox
\`\`\`dataview
LIST FROM [[]] AND !outgoing([[]])
\`\`\`

## Organised
```

**`Technical.md`** (Business vault):
```markdown
# Technical
Design docs, RFCs, architecture notes, code references.

## Inbox
\`\`\`dataview
LIST FROM [[]] AND !outgoing([[]])
\`\`\`

## Organised
```

**`Companies.md`** (Business vault — index of per-company MOCs):
```markdown
# Companies
One entry per organisation. Each links to a per-company MOC.

- [[Amazon]]
- [[T-Systems]]
- [[TSC]]
- [[Parnell Systems]]

## Inbox — unassigned org notes
\`\`\`dataview
LIST FROM [[]] AND !outgoing([[]])
\`\`\`
```

Per-company MOC (e.g. `Amazon.md`) — same inbox pattern, scoped to org:
```markdown
# Amazon
\`\`\`dataview
LIST FROM [[]] AND !outgoing([[]])
\`\`\`
```

**`People.md`** (both vaults):
```markdown
# People
\`\`\`dataview
TABLE length(rows) AS Mentions
FROM ""
WHERE people != null
FLATTEN people
GROUP BY people
SORT length(rows) DESC
\`\`\`
```

**`Interview Prep.md`** (Personal vault — the interview preparation hub):
```markdown
# Interview Prep
STAR stories, competency examples, potential questions, and management learnings for interview use.

## Inbox — newly classified interview notes
\`\`\`dataview
LIST FROM [[]] AND !outgoing([[]])
\`\`\`

## STAR Stories
<!-- Move entries here from inbox, grouped by competency / leadership principle -->

### Customer Obsession

### Ownership

### Delivery & Results

### Invent & Simplify

### Strategic Thinking

### People Leadership

## Potential Questions
<!-- Questions you've been asked or want to prepare for -->

## Evidence Bank — Technical
<!-- Architectural decisions, technical wins, design choices worth citing -->
```

**`Leadership.md`** (Business vault — management knowledge base):
```markdown
# Leadership
OLR notes, performance management records, and management best practices across organisations.

## Inbox — newly classified management notes
\`\`\`dataview
LIST FROM [[]] AND !outgoing([[]])
\`\`\`

## Performance Management
<!-- OLR notes, PIPs, calibration records, individual feedback sessions -->

## Management Best Practices
<!-- Practices and learnings from Amazon, T-Systems, TSC, and other sources -->

## Team Health & Development
<!-- Coaching sessions, career development conversations, succession planning -->
```

**`Job Hunt.md`** (Personal vault — application pipeline tracker):
```markdown
# Job Hunt
Active applications, role research, hiring manager notes, interview stages, post-interview retros.

## Inbox — new application notes
\`\`\`dataview
LIST FROM [[]] AND !outgoing([[]])
\`\`\`

## Active pipeline
\`\`\`dataview
TABLE org AS Company, file.cday AS Started
FROM ""
WHERE type = "application" AND !contains(tags, "rejected") AND !contains(tags, "withdrawn") AND !contains(tags, "offer")
SORT file.cday DESC
\`\`\`

## Offers & closed
<!-- Manually move offers / rejections here -->
```

**`Career.md`** (Personal vault — evidence bank for CV and interviews):
```markdown
# Career
Resume bullets, achievements timeline, certifications, education, talks.

## Inbox
\`\`\`dataview
LIST FROM [[]] AND !outgoing([[]])
\`\`\`

## Achievements timeline
<!-- Chronological list of headline accomplishments — feeds CV bullets -->

## Certifications & education
<!-- AWS certifications, qualifications, courses completed -->

## Public speaking & writing
<!-- Talks given, articles published -->
```

**`Patterns.md`** (Business vault — architecture knowledge separate from work-specific Technical):
```markdown
# Patterns
Reusable architecture and design patterns. Where `[[Technical]]` is "what I did at company X", `[[Patterns]]` is "general design knowledge I should know for system-design interviews".

## Inbox
\`\`\`dataview
LIST FROM [[]] AND !outgoing([[]])
\`\`\`

## Distributed systems
<!-- CAP, consistent hashing, gossip, consensus protocols -->

## Data & storage
<!-- CQRS, event sourcing, sharding, indexing strategies -->

## Service design
<!-- Saga, circuit breaker, bulkhead, rate limiting -->

## Cross-cutting
<!-- Observability, security patterns, deployment patterns -->
```

**`Home.md`** (both vaults — the navigation entry point, links to all other MOCs in this vault):
```markdown
# Home

## Personal vault
- [[Meetings]] — all meeting notes
- [[People]] — everyone mentioned across notes
- [[Personal]] — journals, recipes, personal notes
- [[Reference]] — reference material and how-tos
- [[Interview Prep]] — STAR stories, competency examples, interview questions
- [[Job Hunt]] — active applications and role research
- [[Career]] — resume bullets, achievements, certifications

## Navigation
Start here. Click into any MOC to browse its notes, or use graph view to see the full radial structure.
```

*(Business vault `Home.md` lists `[[Meetings]]`, `[[Technical]]`, `[[Patterns]]`, `[[Companies]]`, `[[People]]`, `[[Projects]]`, `[[Leadership]]` instead.)*

**Also update `UP_MAP` in Unit 5** to reflect the full MOC set:
```python
UP_MAP = {
    "meeting":    "[[Meetings]]",
    "technical":  "[[Technical]]",
    "reference":  "[[Reference]]",
    "person":     "[[People]]",
    "company":    "[[Companies]]",
    "recipe":     "[[Personal]]",
    "journal":    "[[Personal]]",
    "personal":   "[[Personal]]",
    "note":        "[[Personal]]",
    "project":     "[[Projects]]",
    "interview":   "[[Interview Prep]]",
    "management":  "[[Leadership]]",
    "application": "[[Job Hunt]]",
    "career":      "[[Career]]",
    "pattern":     "[[Patterns]]",
}
```

**Verification (smoke test, manual — must pass before declaring Unit 7 done):**

This sequence proves the MOC inbox pattern actually works, end-to-end:

1. Create a throwaway test note `Personal/_moc-smoke-test.md` with frontmatter `up: "[[Meetings]]"` and any body content.
2. Open `Personal/Meetings.md` in Obsidian.
3. **Expected:** `_moc-smoke-test` appears in the Inbox section's Dataview list within ~2 seconds (Dataview refresh interval).
4. Add `[[_moc-smoke-test]]` to the Organised section of `Meetings.md`.
5. **Expected:** `_moc-smoke-test` disappears from the Inbox list on next render.
6. Delete the test note.

Failure mode: if step 3 doesn't surface the note, the `LIST FROM [[]] AND !outgoing([[]])` query isn't resolving `[[]]` to the current file. Diagnose with `LIST FROM [[Meetings]]` literal — if that works but `[[]]` doesn't, the Dataview version may need updating.

Additional verification:
- Graph view shows MOC notes as high-connectivity hubs with spokes radiating outward
- Repeat the smoke test for `Job Hunt.md`, `Interview Prep.md`, and `Leadership.md` (the new MOCs)

---

### Unit 8: Vault Migration Tooling

**Execution target: claude**
**Goal:** CLI that moves all Evernote-imported notes out of the `Evernote/` subfolder structure, routing `context: work` notes to the Business vault and `context: personal` notes to the Personal vault root — both landing flat (no subfolders). End state: zero `Evernote/` folders in either vault.

**Target vault structure post-migration:**
```
Personal/
  Meetings.md          ← MOC
  Personal.md          ← MOC
  People.md            ← MOC
  Reference.md         ← MOC
  [note].md            ← flat, no subfolders
  [note].md
  ...

Business/
  Meetings.md          ← MOC
  Technical.md         ← MOC
  Companies.md         ← MOC
  People.md            ← MOC
  Projects.md          ← MOC
  [note].md            ← flat, no subfolders
  [note].md
  ...
```

**Requirements:** R9–R11 (migration candidates, explicit step, `up:` updated on move).

**Dependencies:** Unit 5 (classification confirmed before migration runs).

**Files:**
- `granolaSync/classify/migrate_vault.py` — new
- `granolaSync/tests/integration/classify/test_migrate_vault.py` — new

**Approach:**

CLI: `python granolaSync/classify/migrate_vault.py --personal <path> --business <path> [--dry-run] [--limit N]`

Two migration passes in one run:

**Pass A — cross-vault migration** (work notes out of Personal):
- Find notes in `Personal/Evernote/` with `context: work`
- Destination: `Business/<filename>.md` (flat root, no subfolder)

**Pass B — intra-vault defragmentation** (personal notes out of Evernote folders):
- Find notes in `Personal/Evernote/` with `context: personal` or `context: education`
- Destination: `Personal/<filename>.md` (flat root, out of Evernote subfolder)

After both passes, if `Personal/Evernote/` is empty → delete it.

Steps for each note:
1. Require `is_classified()` — skip unclassified notes with warning
2. Compute destination path (flat root of target vault)
3. Resolve conflicts: if `<filename>.md` exists in destination, append `_2`, `_3`
4. `shutil.move()` — works across filesystem boundaries
5. `up:` field is already correct from classification (same MOC names in both vaults)
6. Append entry to `migration-log.md` in Business vault root: original path, destination, date

Safety gates:
- `--dry-run` by default (must pass `--confirm` to write)
- `--limit N` for staged rollout
- Never move a note that is not `is_classified()`
- Stop and report on any filesystem error — never silently continue
- Print summary before acting: N work notes → Business, M personal notes → Personal root

**Test scenarios (integration — `tmp_path` with real directory structures):**
- Note in `Personal/Evernote/notes/AWS/` with `context: work` → moves to `Business/` flat root
- Note in `Personal/Evernote/notes/AWS/` with `context: personal` → moves to `Personal/` flat root
- Note already in `Personal/` (not in Evernote subfolder) → skipped (not in migration scope)
- Unclassified note → skipped with warning printed
- Without `--confirm` → no files moved, summary printed
- With `--confirm` and `--dry-run` → `--dry-run` wins, no files moved
- Filename conflict → destination gets `_2` suffix
- After all Evernote notes migrated → `Personal/Evernote/` directory deleted
- `migration-log.md` created in Business vault root with correct entries

**Verification:** `pytest granolaSync/tests/integration/classify/test_migrate_vault.py -v` — all pass.

---

## Test File Map

| Unit | Test file |
|------|-----------|
| 2 | `granolaSync/tests/unit/classify/test_frontmatter.py` |
| 3 | `granolaSync/tests/unit/classify/test_rules_classifier.py` |
| 4 | `granolaSync/tests/unit/classify/test_lm_classifier.py` |
| 5 | `granolaSync/tests/integration/classify/test_classify_vault.py` |
| 6 | `granolaSync/tests/unit/test_export_granola.py` (extend) |
| 8 | `granolaSync/tests/integration/classify/test_migrate_vault.py` |

---

## Sequencing

```
Unit 0 → Unit 0.5 → Unit 1 → Unit 2 → Unit 3 → Unit 4 → Unit 5 → Unit 6
                                                                    ↓
                                                                 Unit 7
                                                                    ↓
                                                                 Unit 8
```

Unit 0.5 (backup) MUST land before Unit 5 starts writing frontmatter. It's parked between Unit 0 and Unit 1 so it happens early and is never skipped under deadline pressure.

Unit 6 can run in parallel with Units 3–5 once Unit 2 is done (it only imports the schema reference, not the classifiers).

Unit 7 is blocked on Unit 5 reaching sufficient classification coverage (not blocked on code — blocked on data). Create hub page stubs earlier if helpful.

---

## Deferred to Implementation

- Exact Ollama model to use (decide in Unit 0 based on JSON compliance test)
- Whether `project` field can be reliably extracted by rules (start with always omitting it; add later if Ollama extraction proves reliable)
- Business vault Dataview plugin version (install in Unit 8 setup; check compatibility with Personal vault v0.5.68 queries)
- Whether `classification-review.md` format should be Markdown table or CSV (start with Markdown table per R6; switch to CSV only if user prefers it after seeing the first output)

---

## Dependencies / Assumptions

- Ollama is installed at `/opt/homebrew/bin/ollama` (confirmed)
- No models are currently pulled (confirmed — `ollama list` showed empty)
- Python 3.14 Homebrew, pip blocked system-wide, requires venv (confirmed)
- `pytest` is the test runner, invoked as bare `pytest` (Homebrew formula, not in Python site-packages)
- Dataview v0.5.68 is installed in Personal vault only
- Business vault exists at `~/Documents/ObsidianVault/Business/`
- iCloud Drive is syncing `~/Documents/` — atomic writes and rate limiting required

---

## Success Criteria (from origin)

- Dataview query `org: "Amazon"` returns only Amazon work notes, not personal notes from AWS folder
- Meetings Homepage shows only notes with `type: meeting` and real body content
- A new Granola export note has complete R2 frontmatter without manual steps
- Review queue reaches zero after user works through it
- Obsidian graph view shows radial structure centred on hub pages
