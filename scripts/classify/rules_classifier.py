"""Extended rules-based classifier for R2 schema.

Produces all R2 frontmatter fields (type, org, context, people, tags) from
note content + filename, returning a confidence score so the caller can
gate on the 0.80 auto-classify threshold from the plan.

Extends `scripts.classify_notes` — does NOT modify it. Imports the existing
WORK/PERSONAL keyword sets and `score_note()` for context derivation when
no org match is found.
"""

from __future__ import annotations

import re
from typing import Any

from scripts.classify_notes import score_note

# Org keyword sets — first hit wins on tie via dict insertion order.
ORG_KEYWORDS: dict[str, list[str]] = {
    "Amazon": [
        "aws", "amazon", "s3", "ec2", "lambda", "cloudwatch", "redshift",
        "iam", "sagemaker", "kindle", "alexa",
    ],
    "T-Systems": ["t-systems", "tsystems", "telekom", "magenta", "deutsche telekom"],
    "TSC": ["tsc", "transport systems", "catapult"],
    "Parnell Systems": ["parnell systems", "allconvos", "voice ai", "granola"],
}

# Type keyword sets — order matters for tie-breaking (meeting before
# technical so "deployment meeting" resolves to meeting).
TYPE_KEYWORDS: dict[str, list[str]] = {
    "meeting": [
        "meeting", "standup", "stand-up", "retrospective", "1-1", "one-on-one",
        "agenda", "action items", "attendees", "minutes",
    ],
    "technical": [
        "architecture", "design doc", "rfc", "api", "schema", "database",
        "implementation", "algorithm", "code review", "pull request", "deployment",
    ],
    "reference": [
        "reference", "cheatsheet", "cheat sheet", "how to", "howto",
        "documentation", "notes on", "summary of", "overview",
    ],
    "recipe": [
        "recipe", "ingredients", "cook", "cooking", "bake", "baking",
        "tablespoon", "teaspoon", "oven", "prep time",
    ],
    "journal": ["today i", "feeling", "reflection", "diary", "personal note"],
    "interview": [
        "star", "situation task action result", "tell me about a time",
        "interview question", "interview prep", "competency", "leadership principle",
        "behavioural question", "behavioral question", "example of when",
        "demonstrate", "accomplishment", "strength", "weakness",
    ],
    "management": [
        "olr", "performance review", "performance management", "pip",
        "direct report", "manager feedback", "calibration", "promotion",
        "talent review", "coaching session", "career development",
        "management practice", "leadership practice", "team health",
        "low performer", "high performer", "succession",
    ],
    "application": [
        "applied to", "job application", "role description",
        "hiring manager", "recruiter", "screening call", "phone screen",
        "onsite", "offer", "rejected", "withdrew application",
        "interview stage", "applied via", "linkedin easy apply",
    ],
    "career": [
        "cv", "resume", "achievements", "certification", "qualification",
        "professional summary", "career timeline", "linkedin profile",
        "education", "degree", "certified", "credentials",
    ],
    "pattern": [
        "design pattern", "architectural pattern", "cqrs", "event sourcing",
        "saga pattern", "circuit breaker", "bulkhead", "cap theorem",
        "consistent hashing", "load balancing", "rate limiting",
        "service mesh", "domain driven", "ddd", "hexagonal", "clean architecture",
    ],
}

# Tag patterns — additive. Each tag fires independently if any of its
# patterns appears (case-insensitive substring match).
TAG_PATTERNS: dict[str, list[str]] = {
    # STAR / interview tags
    "star": ["star story", "situation:", "task:", "action:", "result:"],
    "weakness": ["weakness", "area for improvement", "where i struggled"],
    "failure-story": ["failed", "didn't work", "post-mortem", "incident report"],
    "success-story": ["success story", "shipped on time", "exceeded targets"],
    "behavioral": ["behavioral question", "behavioural question", "tell me about a time"],
    "technical-deep-dive": ["deep dive", "technical deep", "low-level design"],
    "system-design": ["system design", "architecture review", "design doc"],
    "coding": ["leetcode", "coding round", "algorithm question"],
    # AWS Leadership Principles
    "aws-lp/customer-obsession": [
        "customer obsession", "customer first", "customer escalation",
    ],
    "aws-lp/ownership": ["ownership", "own the outcome", "above and beyond"],
    "aws-lp/invent-simplify": [
        "invent and simplify", "simplification", "novel approach",
    ],
    "aws-lp/are-right-a-lot": [
        "are right, a lot", "right a lot", "good judgement", "good judgment",
    ],
    "aws-lp/learn-and-be-curious": [
        "learn and be curious", "continual learning", "self-taught",
    ],
    "aws-lp/hire-and-develop": [
        "hire and develop", "develop the best", "raised the bar",
    ],
    "aws-lp/insist-on-highest-standards": [
        "highest standards", "insist on quality", "raising the bar",
    ],
    "aws-lp/think-big": ["think big", "bold direction", "long term vision"],
    "aws-lp/bias-for-action": ["bias for action", "speed matters", "decisive"],
    "aws-lp/frugality": ["frugality", "do more with less"],
    "aws-lp/earn-trust": [
        "earn trust", "vocally self-critical", "treat others with respect",
    ],
    "aws-lp/dive-deep": ["dive deep", "root cause", "investigation"],
    "aws-lp/have-backbone": [
        "disagreed", "pushed back", "challenged", "have backbone",
        "disagree and commit",
    ],
    "aws-lp/deliver-results": [
        "delivered", "shipped", "meeting deadlines", "deliver results",
    ],
    "aws-lp/strive-to-be-earths-best-employer": [
        "best employer", "empathy", "psychological safety",
    ],
    "aws-lp/success-and-scale": ["success and scale", "broad responsibility"],
    # Job hunt
    "applied": ["applied to", "applied via"],
    "interviewing": ["interview scheduled", "phone screen", "onsite scheduled"],
    "offer": ["offer received", "offer letter"],
    "rejected": ["rejected", "did not progress"],
    "withdrawn": ["withdrew application", "withdrew from"],
    # Quality
    "polished": ["[polished]", "tag: polished"],
    "draft": ["[draft]", "tag: draft", "wip", "work in progress"],
}

# Capitalised name-pair regex: "John Smith", "John Quincy Adams" — but not
# "AWS Deployment" (no lowercase after the caps) or "Tuesday" (single word).
PEOPLE_PATTERN = re.compile(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b")

# Weekdays and months — common false positives for the name-pair regex.
# A whole bigram is dropped if any token is in this set ("Tuesday Meeting"
# disappears entirely, not just the "Tuesday" half).
_PEOPLE_FILTER: frozenset[str] = frozenset({
    "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday",
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
})

_WORK_ORGS: frozenset[str] = frozenset({"Amazon", "T-Systems", "TSC", "Parnell Systems"})


def _score_keywords(text_lower: str, table: dict[str, list[str]]) -> dict[str, int]:
    """Count how many keywords from each category appear in lower-cased text.

    Each keyword counts once per category regardless of multiple occurrences —
    matching the existing `score_note()` pattern in classify_notes.py.
    """
    return {
        category: sum(1 for kw in keywords if kw in text_lower)
        for category, keywords in table.items()
    }


def _argmax_first(scores: dict[str, int]) -> str | None:
    """Return the key with the highest score, ties broken by dict insertion
    order. Returns None if all scores are zero."""
    if not scores or max(scores.values()) == 0:
        return None
    top_score = max(scores.values())
    for key, score in scores.items():
        if score == top_score:
            return key
    return None  # unreachable


def _confidence(scores: dict[str, int]) -> float:
    """Top-score proportion. Zero when no category scored."""
    total = sum(scores.values())
    if total == 0:
        return 0.0
    return max(scores.values()) / total


def _extract_people(body: str) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for match in PEOPLE_PATTERN.findall(body):
        if any(token in _PEOPLE_FILTER for token in match.split()):
            continue
        if match in seen:
            continue
        seen.add(match)
        out.append(match)
    return out


def _extract_tags(text_lower: str) -> list[str]:
    return [
        tag
        for tag, patterns in TAG_PATTERNS.items()
        if any(p in text_lower for p in patterns)
    ]


def _context_for(org: str, work_score: float, personal_score: float) -> str:
    if org in _WORK_ORGS:
        return "work"
    if org == "Personal":
        return "personal"
    # Fallback for any org outside the known set — pick by content score.
    if work_score > personal_score:
        return "work"
    return "personal"


def classify(title: str, body: str, folder_hint: str = "") -> dict[str, Any]:
    """Classify a note into R2 schema fields.

    Returns a dict with: type, org, context, people, tags, confidence, reason.

    `folder_hint` is the Evernote folder name (e.g. "AWS"). It is used ONLY
    as a tie-breaker when content has no org keywords — content always wins.
    """
    combined = f"{title}\n{body}"
    combined_lower = combined.lower()
    folder_lower = folder_hint.lower()

    # Org detection — content first, folder hint only when content is silent.
    org_scores = _score_keywords(combined_lower, ORG_KEYWORDS)
    org = _argmax_first(org_scores)
    org_confidence = _confidence(org_scores)
    if org is None:
        hint_scores = _score_keywords(folder_lower, ORG_KEYWORDS)
        hint_org = _argmax_first(hint_scores)
        if hint_org is not None:
            org = hint_org
            org_confidence = 0.5  # low but non-zero — flags note for review
        else:
            org = "Personal"
            org_confidence = 0.0

    # Type detection.
    type_scores = _score_keywords(combined_lower, TYPE_KEYWORDS)
    type_ = _argmax_first(type_scores)
    type_confidence = _confidence(type_scores)

    work_score, personal_score, _ = score_note(title, body)

    if type_ is None:
        # No type keyword matched — pick "personal" if the body leans
        # personal, otherwise fall back to the generic "note".
        type_ = "personal" if personal_score > work_score else "note"
        type_confidence = 0.0

    context = _context_for(org, work_score, personal_score)
    people = _extract_people(body)
    tags = _extract_tags(combined_lower)
    confidence = min(org_confidence, type_confidence)

    reason = (
        f"org={org} (score {org_scores.get(org, 0)}), "
        f"type={type_} (score {type_scores.get(type_, 0)})"
    )

    return {
        "type": type_,
        "org": org,
        "context": context,
        "people": people,
        "tags": tags,
        "confidence": confidence,
        "reason": reason,
    }
