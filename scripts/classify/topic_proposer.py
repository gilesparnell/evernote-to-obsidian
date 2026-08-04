"""U6 Topic Proposer — self-extending topic discovery.

Nightly, after classification, this gathers notes that matched no registered
topic, clusters them deterministically by shared entities/keywords, scores each
cluster with a deterministic confidence, then splits three ways: auto-create +
synthesise high-confidence clusters, propose borderline ones in the gardener
report, and hold sub-floor ones in a knowledge-item ledger.

Built incrementally per the U6 plan. This module holds the pure detection +
scoring logic; chain wiring lives in nightly_chain and reporting in gardener.
"""

from __future__ import annotations

import hashlib
import re
import sys
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.classify.classify_vault import _strip_frontmatter
from scripts.classify.collect_topic import (
    _matched_aliases,
    _prefers,
    iter_source_notes,
)
from scripts.classify.frontmatter import read_frontmatter
from scripts.classify.topics import Topic, load_topics

_SMART_APOSTROPHES = str.maketrans({"’": "'", "‘": "'", "‛": "'", "`": "'"})
_TOKEN_RE = re.compile(r"[a-z0-9]+")
_MIN_TOKEN_LEN = 3


@dataclass(frozen=True)
class NoteRef:
    """A candidate note (matched no topic) plus its folded clustering signals."""

    path: Path
    rel: str
    title: str
    people: frozenset[str]
    tags: frozenset[str]
    org: str | None
    tokens: frozenset[str]


# --- folding / tokenising --------------------------------------------------

def _fold(text: str) -> str:
    folded = unicodedata.normalize("NFKD", text.translate(_SMART_APOSTROPHES))
    return folded.casefold()


def _tokens(text: str) -> frozenset[str]:
    return frozenset(
        tok for tok in _TOKEN_RE.findall(_fold(text)) if len(tok) >= _MIN_TOKEN_LEN
    )


def _folded_list(value: object) -> frozenset[str]:
    if not isinstance(value, list):
        return frozenset()
    return frozenset(_fold(item) for item in value if isinstance(item, str) and item)


# --- recency ---------------------------------------------------------------

def _as_aware(dt: datetime) -> datetime:
    return dt.astimezone() if dt.tzinfo is None else dt


def _note_time(path: Path, fm: dict) -> datetime:
    """Best-effort note timestamp: frontmatter updated/created, else mtime."""
    for key in ("updated", "created"):
        raw = fm.get(key)
        if isinstance(raw, datetime):  # must precede date — datetime subclasses date
            return _as_aware(raw)
        if isinstance(raw, date):  # YAML bare date (no time component)
            return _as_aware(datetime.combine(raw, time.min))
        if isinstance(raw, str) and raw.strip():
            try:
                return _as_aware(datetime.fromisoformat(raw.strip()))
            except ValueError:
                continue
    return datetime.fromtimestamp(path.stat().st_mtime).astimezone()


# --- gathering (Unit 1) ----------------------------------------------------

def _matches_any_topic(filename: str, body: str, topics: list[Topic]) -> bool:
    return any(
        _matched_aliases(aliases=t.aliases, filename=filename, body=body)
        for t in topics
    )


def _build_noteref(vault: Path, path: Path, fm: dict, body: str) -> NoteRef:
    title = fm.get("title")
    org = fm.get("org")
    return NoteRef(
        path=path,
        rel=path.relative_to(vault).as_posix(),
        title=title if isinstance(title, str) and title else path.stem,
        people=_folded_list(fm.get("people")),
        tags=_folded_list(fm.get("tags")),
        org=_fold(org) if isinstance(org, str) and org else None,
        tokens=_tokens(f"{title if isinstance(title, str) else path.stem}\n{body}"),
    )


def gather_unregistered_notes(
    vault: Path,
    *,
    recency_days: int = 30,
    full: bool = False,
    now: datetime | None = None,
) -> list[NoteRef]:
    """Return notes matching no registered topic, deduped and recency-windowed.

    Exhaustive (never sampled). Reuses ``iter_source_notes`` (skips wiki/,
    backups, dotdirs) and ``_matched_aliases`` so the candidate universe is
    exactly the classifier's. Yarle numbered copies collapse to the base note.
    """
    topics = load_topics(vault)
    horizon = None
    if not full:
        anchor = _as_aware(now) if now is not None else datetime.now().astimezone()
        horizon = anchor - timedelta(days=recency_days)

    by_body: dict[str, NoteRef] = {}
    for path in iter_source_notes(vault):
        text = path.read_text(encoding="utf-8")
        body = _strip_frontmatter(text)
        if _matches_any_topic(path.name, body, topics):
            continue

        fm = read_frontmatter(path)
        if horizon is not None and _note_time(path, fm) < horizon:
            continue

        ref = _build_noteref(vault, path, fm, body)
        body_sha = hashlib.sha256(body.encode("utf-8")).hexdigest()
        existing = by_body.get(body_sha)
        if existing is None or _prefers(ref.rel, existing.rel):
            by_body[body_sha] = ref

    return sorted(by_body.values(), key=lambda ref: ref.rel)
