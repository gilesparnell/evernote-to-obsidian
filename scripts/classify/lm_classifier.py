"""LM Studio classifier — Gemma 4 E4B via OpenAI-compatible function calling.

Used by the batch pipeline (Unit 5) only when rules confidence is below the
0.80 auto-classify threshold. The function-calling schema constrains output
to canonical enum values so the response is always parseable.

The LM Studio server is expected on http://localhost:1234/v1. On ANY failure
(server down, timeout, no tool_calls in response, malformed JSON, parse
error) `classify()` returns a low-confidence "unavailable" result rather
than raising — the pipeline gracefully drops to the review queue.

LM Studio gotcha (verified Unit 0): `tool_choice` must be a string
("none" / "auto" / "required"); the OpenAI object form returns HTTP 400
"Invalid tool_choice type: 'object'". With only one tool exposed, "required"
is functionally identical to forcing the named function.
"""

from __future__ import annotations

import json
from typing import Any

import openai

LM_STUDIO_BASE_URL = "http://localhost:1234/v1"
LM_STUDIO_MODEL = "google/gemma-4-e4b"

_TYPE_ENUM = [
    "meeting", "note", "technical", "reference", "person", "company",
    "project", "recipe", "journal", "personal", "interview", "management",
    "application", "career", "pattern",
]
_ORG_ENUM = [
    "Amazon", "T-Systems", "TSC", "Parnell Systems", "Personal", "Unknown",
]
_CONTEXT_ENUM = ["work", "personal", "education", "unknown"]

CLASSIFY_SCHEMA: dict[str, Any] = {
    "name": "classify_note",
    "parameters": {
        "type": "object",
        "properties": {
            "type": {"type": "string", "enum": _TYPE_ENUM},
            "org": {"type": "string", "enum": _ORG_ENUM},
            "context": {"type": "string", "enum": _CONTEXT_ENUM},
            "people": {"type": "array", "items": {"type": "string"}},
            "tags": {"type": "array", "items": {"type": "string"}},
            "confidence": {"type": "number"},
            "reason": {"type": "string"},
        },
        "required": ["type", "org", "context", "people", "tags", "confidence"],
    },
}

_SYSTEM_PROMPT = """You classify Obsidian markdown notes into a fixed schema by reading the title and body.

TYPE guidance:
- meeting: Attendees, Agenda, action items, standup, retrospective, minutes, 1-1
- technical: architecture, design doc, RFC, API/schema/algorithm notes
- recipe: cooking/baking, ingredient lists
- interview: STAR stories (Situation/Task/Action/Result), competency examples, behavioural questions
- management: OLR, performance review, PIP, direct report, calibration, low/high performer
- application: applied to X, job application, phone screen, hiring manager
- career: CV, resume, certifications, achievements timeline
- pattern: design patterns (CQRS, event sourcing, saga, CAP, etc.) for system design
- journal: diary / reflection / personal-note style
- personal: family, birthdays, kids, household
- note: catch-all when no other type fits

ORG guidance — look in body for these signals:
- Amazon: AWS, S3, EC2, Lambda, CloudWatch, IAM, Kindle, Alexa, SageMaker
- T-Systems: T-Systems, Telekom, Magenta, Deutsche Telekom
- TSC: TSC, Transport Systems Catapult
- Parnell Systems: AllConvos, granolaSync, voice AI work
- Personal: family / leisure / personal life
- Unknown: only when there is no organisation signal at all

CONTEXT: work | personal | education | unknown. Employer-related notes are work; family/recipes/health are personal.

PEOPLE: proper names (First Last) extracted from the body. Skip weekday/month words.

TAGS: include applicable identifiers — "star" for STAR-format stories, "draft"/"polished" for quality markers, "aws-lp/<principle>" for AWS leadership principle hits (customer-obsession, ownership, dive-deep, etc.), and "applied"/"interviewing"/"offer"/"rejected" for job-hunt stage markers.

CONFIDENCE: 0.0-1.0. Use 0.9+ only when both type and org are unambiguous; use 0.3-0.6 when the signal is weak.

Always call the classify_note tool."""


def _unavailable(reason: str) -> dict[str, Any]:
    """Return a degraded result that keeps callers downstream safe.

    Confidence is 0.0 so the batch pipeline drops the note into the review
    queue. Org defaults to Personal so any subsequent vault-routing logic
    keeps the note in the personal vault rather than mis-routing it.
    """
    return {
        "type": "note",
        "org": "Personal",
        "context": "personal",
        "people": [],
        "tags": [],
        "confidence": 0.0,
        "reason": f"lm-studio unavailable: {reason}",
    }


def classify(title: str, body: str, folder_hint: str = "") -> dict[str, Any]:
    """Classify a note via LM Studio + Gemma 4 E4B function calling.

    Never raises. On any failure returns a result with confidence 0.0 and a
    "lm-studio unavailable" reason — the caller treats this as "drop to
    review queue".
    """
    prompt = (
        f"Title: {title}\n"
        f"Folder hint: {folder_hint or '(none)'}\n"
        f"Body:\n{body}"
    )

    try:
        client = openai.OpenAI(base_url=LM_STUDIO_BASE_URL, api_key="lm-studio")
        response = client.chat.completions.create(
            model=LM_STUDIO_MODEL,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            tools=[{"type": "function", "function": CLASSIFY_SCHEMA}],
            tool_choice="required",
        )
        tool_calls = response.choices[0].message.tool_calls
        if not tool_calls:
            return _unavailable("no tool_calls in response")
        args = json.loads(tool_calls[0].function.arguments)
    except Exception as exc:
        return _unavailable(f"{type(exc).__name__}: {exc}")

    # Normalise the parsed args — schema enforcement should make these always
    # present, but Gemma occasionally drops optional list fields.
    people = args.get("people") or []
    tags = args.get("tags") or []
    confidence = min(float(args.get("confidence", 0.0)), 1.0)

    org = args.get("org", "Personal")
    context = args.get("context", "personal")
    if org == "Unknown" and context == "unknown":
        # Model couldn't determine either — collapse to safe defaults.
        org, context = "Personal", "personal"

    return {
        "type": args.get("type", "note"),
        "org": org,
        "context": context,
        "people": people,
        "tags": tags,
        "confidence": confidence,
        "reason": args.get("reason", "classified by lm-studio"),
    }
