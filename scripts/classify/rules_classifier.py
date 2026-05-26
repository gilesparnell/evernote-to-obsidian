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
        # Interview-specific phrases. Generic words like 'demonstrate',
        # 'strength', 'weakness', 'accomplishment' were removed 2026-05-14
        # because they hit too many ordinary business notes (false positives
        # in AWS like 'Brody's Departure', 'Builder Tools coming to SYD').
        "star story", "situation task action result", "tell me about a time",
        "interview question", "interview prep", "leadership principle",
        "behavioural question", "behavioral question",
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
        # Career-specific phrases. Generic terms 'credentials', 'education',
        # 'degree', 'certified' were removed 2026-05-14 because they fire
        # on AWS technical notes (AWS credentials, certification courses).
        "cv", "resume",  "professional summary", "career timeline",
        "linkedin profile", "achievements summary",
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

# Title-pattern rules — fire on the note's filename pattern. Match the
# beginning of the title (re.IGNORECASE). When a rule matches, type is
# assigned with `_TITLE_RULE_CONFIDENCE`, bypassing the share-of-total
# keyword math. Order matters — first match wins, so put more specific
# patterns first.
_TITLE_TYPE_RULES: list[tuple[re.Pattern[str], str]] = [
    # 1-on-1 meetings: '1-1 X', '1:1 X', '1_1 X', '1 1 X' all common after
    # Evernote export. `(?:\b|_)` because Evernote's underscore-as-colon
    # substitution turns 'Interview: Foo' into 'Interview_ Foo'.
    (re.compile(r"^\s*1[-:_ ]?1(?:\b|_)", re.IGNORECASE), "meeting"),
    # Recurring meetings.
    (re.compile(r"^\s*standup(?:\b|_)", re.IGNORECASE), "meeting"),
    (re.compile(r"^\s*(weekly|daily|monthly)\s+(sync|standup|catch[- ]?up|meeting|review|update)?", re.IGNORECASE), "meeting"),
    (re.compile(r"^\s*(catch[- ]?up|sync)\s+with(?:\b|_)", re.IGNORECASE), "meeting"),
    # Sprint planning / review — agile cadence.
    (re.compile(r"^\s*sprint(?:\b|_)", re.IGNORECASE), "meeting"),
    # Interviews / hiring.
    (re.compile(r"^\s*(interview|phone\s*screen|onsite|debrief)(?:\b|_)", re.IGNORECASE), "interview"),
    # Management cadences.
    (re.compile(r"^\s*(olr|pip)(?:\b|_)", re.IGNORECASE), "management"),
    (re.compile(r"^\s*(performance\s+review|annual\s+review|talent\s+review|calibration)(?:\b|_)", re.IGNORECASE), "management"),
    (re.compile(r"^\s*yearly(?:\b|_)", re.IGNORECASE), "management"),
    # Goal-tracking titles, including '20YY ... Goal Tracker' and 'H1 Goals'.
    (re.compile(r"\b(goal\s+tracker|annual\s+goals?|quarterly\s+goals?|h[12]\s+goals?)(?:\b|_)", re.IGNORECASE), "management"),
    # Bare 'Calibration' anywhere (real example: '2024 NSS Q1 Calibration').
    (re.compile(r"\bcalibration(?:\b|_)", re.IGNORECASE), "management"),
    # AWS-specific event references.
    (re.compile(r"\bre[-:/\\]?invent(?:\b|_)", re.IGNORECASE), "reference"),
    (re.compile(r"^\s*(\d{4}\s+)?(summit|conference)(?:\b|_)", re.IGNORECASE), "reference"),
    # Roadmaps and product/team planning docs.
    (re.compile(r"^\s*roadmap(?:\b|_)", re.IGNORECASE), "reference"),
    # Evernote-captured screenshots — reference snapshots.
    (re.compile(r"^\s*screenshot(?:\b|_)", re.IGNORECASE), "reference"),
    # Sales Kick-Off events.
    (re.compile(r"^\s*sko(?:\b|_)", re.IGNORECASE), "reference"),
    # AWS service-name title prefix — bare-service-named notes are
    # technical content by construction. Anchored to start so "Meeting
    # about EC2" still resolves to meeting via keywords. Mined from
    # chunk-3 review queue: EC2 alone was 37 / 566.
    (re.compile(
        r"^\s*("
        r"EC2|S3|IAM|VPC|EKS|ECS|RDS|DynamoDB|CloudWatch|CloudFormation|"
        r"Lambda|Athena|SageMaker|Redshift|Kinesis|SQS|SNS|Bedrock|Glue|"
        r"Step\s+Functions|EventBridge|CodePipeline|CodeBuild|CodeDeploy|"
        r"API\s+Gateway|ALB|ELB|NLB|Route\s*53|CloudFront|ElastiCache"
        r")(?:\b|_)",
        re.IGNORECASE,
    ), "technical"),
    # Evernote web-clipper artefacts. When the user clipped a PDF or URL
    # via cursor selection, Evernote auto-prepended "Cursor and " to the
    # title. These are clippings, not technical content — 107 / 566 of
    # chunk-3 review queue.
    (re.compile(r"^\s*cursor\s+and(?:\b|_)", re.IGNORECASE), "reference"),
    # GoToWebinar screencap notes — 9+ / 566 of chunk-3 review queue.
    (re.compile(r"^\s*gotowebinar(?:\b|_)", re.IGNORECASE), "reference"),
    # Evernote "Inbox – email@host" email-to-Evernote exports. Requires
    # a dash separator so a bare "Inbox" or "Inbox cleanup" stays free
    # to fall through to keyword scoring. 8 / 566 of chunk-3 review queue.
    (re.compile(r"^\s*inbox\s*[–\-]\s*", re.IGNORECASE), "reference"),
    # Numeric image filenames (Evernote camera-export shape). 8+ digits
    # then .jpg/.png/.heic — distinguishes "20180412093715.jpg" (yes)
    # from "1234 notes.jpg" (no). 21 / 566 of chunk-3 review queue.
    (re.compile(r"^\s*\d{8,}\.(?:jpe?g|png|heic|gif)\b", re.IGNORECASE), "reference"),
]

# Confidence assigned when a title rule fires. Below 1.0 so a strong
# competing keyword signal can still win in `classify()` via the
# min(org_confidence, type_confidence) gate, but high enough to clear
# the 0.80 auto-classify threshold when combined with a confident org.
_TITLE_RULE_CONFIDENCE = 0.95

# --- Body-shape rules (plan 2026-05-26-001) ---
#
# Three rules auto-classify bodies that are JUST an embed (image / URL /
# audio / PDF) as type=clipping. One rule (`should_purge_by_body_shape`)
# signals to the pipeline that a body is too short to be worth keeping —
# the pipeline then hard-deletes the file. Mined from 566-note chunk-3
# review queue analysis: 332 single-embed bodies + 75 tiny bodies = 407
# of 566 review-queue entries pre-empted before the LM was ever called.

# Body that is JUST an image embed (Skitch screencap, IMG_*.jpg, etc.).
_BODY_IMAGE_ONLY_RE = re.compile(r"^\s*!\[[^\]]*\]\([^)]+\)\s*$")

# Body that is JUST a URL (bare or angle-bracketed Markdown autolink).
_BODY_URL_ONLY_RE = re.compile(r"^\s*<?https?://\S+?>?\s*$")

# Body that is JUST an Evernote-exported audio embed (.m4a / .mp3 / .wav).
_BODY_AUDIO_EMBED_RE = re.compile(
    r"^\s*\[Evernote\s+\d{8,}[^\]]*\.(?:m4a|mp3|wav)\]\([^)]+\)\s*$",
    re.IGNORECASE,
)

# Body that is JUST a PDF embed (Evernote one-page PDF clippings).
_BODY_PDF_EMBED_RE = re.compile(
    r"^\s*!\[[^\]]*\.pdf[^\]]*\]\([^)]+\)\s*$",
    re.IGNORECASE,
)

# Strip set for the tiny-body check: removes structural Markdown chars
# so the remaining length reflects semantic content. Keeps URL/path
# contents inside `(...)` — those count, even if they're not user prose,
# because operator decision (2026-05-26) is that 30 stripped chars is
# the threshold to KEEP not DELETE.
_BODY_STRIP_MARKDOWN_RE = re.compile(r"[*_#>\[\]()\\\n\t]")

_TINY_BODY_MAX_CHARS = 30
_BODY_SHAPE_CONFIDENCE = 0.85


def should_purge_by_body_shape(body: str) -> bool:
    """True iff the body has < 30 chars of semantic content after stripping
    Markdown wrappers. Includes the zero-length case (empty / whitespace-
    only files) per operator decision 2026-05-26 — those notes are junk by
    definition.

    The caller (classify_vault.py) is responsible for hard-deleting the
    file and appending to the deletion manifest. This function only
    *detects* tininess; it does not act on it.

    NOTE: an image-only body strips to almost nothing (`!xpath.png` and
    similar), so this function will return True for image-only bodies.
    The pipeline must check the clipping rules FIRST and only fall back
    to purge if no clipping rule matched. See TestBodyShapeOrdering."""
    stripped = _BODY_STRIP_MARKDOWN_RE.sub("", body).strip()
    return len(stripped) < _TINY_BODY_MAX_CHARS


def _classify_by_body_shape(
    body: str, folder_hint: str
) -> dict[str, Any] | None:
    """Return a full classify() result dict for clipping-shape bodies, or
    None when no shape matches. Org comes from the folder hint via the
    same logic as the main classify() function.

    Order matters — image is checked before audio/PDF embeds because the
    embed regexes are stricter and would fail earlier; check the most
    common shape first to short-circuit fast."""
    if _BODY_IMAGE_ONLY_RE.match(body):
        # PDF check happens via _BODY_IMAGE_ONLY_RE too (PDFs land as
        # image embeds with .pdf in the alt text). The reason string
        # distinguishes them for the review HTML / sample reports.
        if _BODY_PDF_EMBED_RE.match(body):
            reason = "body-shape: PDF embed (clipping)"
        else:
            reason = "body-shape: single image (clipping)"
    elif _BODY_URL_ONLY_RE.match(body):
        reason = "body-shape: single URL (clipping)"
    elif _BODY_AUDIO_EMBED_RE.match(body):
        reason = "body-shape: Evernote audio embed (clipping)"
    else:
        return None

    # Org inference mirrors the folder-hint fallback path in classify().
    folder_lower = folder_hint.lower()
    hint_scores = _score_keywords(folder_lower, ORG_KEYWORDS)
    hint_org = _argmax_first(hint_scores)
    if hint_org is not None:
        org = hint_org
    else:
        org = "Personal"

    context = "work" if org in _WORK_ORGS else "personal"

    return {
        "type": "clipping",
        "org": org,
        "context": context,
        "people": [],
        "tags": [],
        "confidence": _BODY_SHAPE_CONFIDENCE,
        "reason": reason,
    }

# Minimum keyword-score for the rules cascade to auto-classify on
# keywords alone. Without this, a note hitting ONE generic keyword
# (e.g. 'credentials' from career, 'demonstrate' from interview) gets
# share-of-total = 1.0 and lands in the wrong MOC. Single-keyword
# matches now get confidence 0.5 — below the 0.80 auto-classify gate —
# so the cascade routes them to the LM for real judgement.
_MIN_KEYWORD_SCORE_FOR_CONFIDENCE = 2
_SINGLE_KEYWORD_CONFIDENCE = 0.5


def _title_type_match(title: str) -> str | None:
    """Return the type tag if the title matches a known shortcut pattern,
    else None. First-match-wins order from `_TITLE_TYPE_RULES`."""
    for pattern, type_tag in _TITLE_TYPE_RULES:
        if pattern.search(title):
            return type_tag
    return None


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

    # Body-shape rules (plan 2026-05-26-001). Bodies that are JUST an
    # embed (image / URL / audio / PDF) classify as clipping with high
    # confidence and skip the keyword cascade entirely. These signals are
    # stronger than any title keyword — a "Standup notes" title with an
    # image-only body is a clipping, not a meeting.
    body_shape_result = _classify_by_body_shape(body, folder_hint)
    if body_shape_result is not None:
        return body_shape_result

    # Org detection — content first, folder hint when content is silent.
    org_scores = _score_keywords(combined_lower, ORG_KEYWORDS)
    org = _argmax_first(org_scores)
    org_confidence = _confidence(org_scores)
    if org is None:
        hint_scores = _score_keywords(folder_lower, ORG_KEYWORDS)
        hint_org = _argmax_first(hint_scores)
        if hint_org is not None:
            # Folder name explicitly matches an org keyword (e.g. "AWS",
            # "T-Systems", "TSC") — a strong signal in the Evernote layout
            # where work was filed by employer.
            org = hint_org
            org_confidence = 0.95
        else:
            org = "Personal"
            org_confidence = 0.0

    # Type detection — title-pattern rules first (high-confidence shortcuts),
    # falling back to keyword scoring when no title rule matches.
    title_rule_type = _title_type_match(title)
    if title_rule_type is not None:
        type_ = title_rule_type
        type_confidence = _TITLE_RULE_CONFIDENCE
        type_scores = {type_: 1}  # so reason string has a sensible score
    else:
        type_scores = _score_keywords(combined_lower, TYPE_KEYWORDS)
        type_ = _argmax_first(type_scores)
        if type_ is not None and type_scores[type_] >= _MIN_KEYWORD_SCORE_FOR_CONFIDENCE:
            type_confidence = _confidence(type_scores)
        elif type_ is not None:
            # Single-keyword match — likely false positive. Set confidence
            # below the auto-classify gate so the cascade routes to LM.
            type_confidence = _SINGLE_KEYWORD_CONFIDENCE
        else:
            type_confidence = 0.0  # _argmax_first returned None

    work_score, personal_score, _ = score_note(title, body)

    if type_ is None:
        # No keyword OR title rule matched — pick "personal" if the body
        # leans personal, otherwise fall back to the generic "note".
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
