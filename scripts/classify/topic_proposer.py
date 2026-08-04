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
import math
import re
import sys
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from itertools import combinations
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


@dataclass(frozen=True)
class Cluster:
    """A cohesive group of unregistered notes sharing categorical anchors."""

    members: tuple[NoteRef, ...]
    anchors: frozenset[str]  # anchors shared by a majority of members (namespaced)
    dominant_anchor: str  # the single most common anchor (for naming/slug fallback)
    anchor_density: float  # fraction of member pairs sharing an anchor (0..1)
    cohesion: float  # mean pairwise IDF-weighted-Jaccard of member tokens (0..1)


# Clustering thresholds (consolidated into ProposerConfig in Unit 3).
_MIN_CLUSTER_SIZE = 3
_MIN_DENSITY = 0.7

# Anchors so generic they carry no thematic signal — excluded from the gate.
_GENERIC_TAGS = frozenset(
    {"draft", "todo", "inbox", "clipping", "reference", "note", "untitled"}
)
_GENERIC_ORGS = frozenset({"unknown", "personal", "none", ""})


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


# --- clustering (Unit 2) ---------------------------------------------------

def _anchors(ref: NoteRef) -> frozenset[str]:
    """Namespaced categorical anchors — the only signal that forms an edge.

    Tokens deliberately are NOT anchors: text overlap strengthens confidence
    (Unit 3) but never *creates* a cluster on its own (the AND-gate that
    defeats incidental-token junk merges).
    """
    anchors = {f"person:{p}" for p in ref.people}
    anchors |= {f"tag:{t}" for t in ref.tags if t not in _GENERIC_TAGS}
    if ref.org and ref.org not in _GENERIC_ORGS:
        anchors.add(f"org:{ref.org}")
    return frozenset(anchors)


def _idf(notes: list[NoteRef]) -> dict[str, float]:
    n = len(notes)
    df: dict[str, int] = {}
    for ref in notes:
        for tok in ref.tokens:
            df[tok] = df.get(tok, 0) + 1
    # Smoothed IDF: common tokens (high df) approach zero weight.
    return {tok: math.log((n + 1) / (count + 1)) + 1.0 for tok, count in df.items()}


def _weighted_jaccard(a: NoteRef, b: NoteRef, idf: dict[str, float]) -> float:
    shared = a.tokens & b.tokens
    union = a.tokens | b.tokens
    if not union:
        return 0.0
    num = sum(idf.get(tok, 1.0) for tok in shared)
    den = sum(idf.get(tok, 1.0) for tok in union)
    return num / den if den else 0.0


def _density(members: set[int], adj: dict[int, set[int]]) -> float:
    n = len(members)
    if n < 2:
        return 0.0
    edges = sum(1 for i, j in combinations(sorted(members), 2) if j in adj[i])
    return edges / (n * (n - 1) / 2)


def _components(nodes: list[int], adj: dict[int, set[int]]) -> list[set[int]]:
    seen: set[int] = set()
    comps: list[set[int]] = []
    for start in nodes:
        if start in seen:
            continue
        stack = [start]
        comp: set[int] = set()
        while stack:
            node = stack.pop()
            if node in seen:
                continue
            seen.add(node)
            comp.add(node)
            stack.extend(adj[node] - seen)
        comps.append(comp)
    return comps


def _dense_core(
    comp: set[int], adj: dict[int, set[int]], min_size: int, min_density: float
) -> set[int] | None:
    """Peel the least-connected member until the group is a near-clique.

    Complete-linkage-style: a loose chain (density below the floor) is thinned
    until a dense core remains, or it drops below min_size and is discarded.
    """
    members = set(comp)
    while len(members) >= min_size:
        if _density(members, adj) >= min_density:
            return members
        victim = min(members, key=lambda m: (len(adj[m] & members), m))
        members.discard(victim)
    return None


def _build_cluster(members: set[int], notes: list[NoteRef], idf: dict[str, float],
                   adj: dict[int, set[int]]) -> Cluster:
    refs = tuple(sorted((notes[i] for i in members), key=lambda r: r.rel))
    # Anchors shared by a majority of members; dominant = most common.
    counts: dict[str, int] = {}
    for i in members:
        for anchor in _anchors(notes[i]):
            counts[anchor] = counts.get(anchor, 0) + 1
    majority = (len(members) + 1) // 2
    shared = frozenset(a for a, c in counts.items() if c >= majority)
    dominant = max(counts, key=lambda a: (counts[a], a))
    pairs = list(combinations(sorted(members), 2))
    cohesion = (
        sum(_weighted_jaccard(notes[i], notes[j], idf) for i, j in pairs) / len(pairs)
        if pairs
        else 0.0
    )
    return Cluster(
        members=refs,
        anchors=shared or frozenset({dominant}),
        dominant_anchor=dominant,
        anchor_density=_density(members, adj),
        cohesion=cohesion,
    )


def cluster_notes(
    notes: list[NoteRef],
    *,
    min_size: int = _MIN_CLUSTER_SIZE,
    min_density: float = _MIN_DENSITY,
) -> list[Cluster]:
    """Group unregistered notes into cohesive near-clique clusters.

    An edge exists only between notes sharing a specific categorical anchor;
    clusters must be near-cliques (density-gated) so a chain of pairwise links
    never welds unrelated notes together. Singletons/pairs stay unclustered.
    """
    if len(notes) < min_size:
        return []

    idf = _idf(notes)
    anchor_sets = [_anchors(ref) for ref in notes]
    adj: dict[int, set[int]] = {i: set() for i in range(len(notes))}
    for i, j in combinations(range(len(notes)), 2):
        if anchor_sets[i] & anchor_sets[j]:
            adj[i].add(j)
            adj[j].add(i)

    clusters: list[Cluster] = []
    for comp in _components(list(range(len(notes))), adj):
        if len(comp) < min_size:
            continue
        core = _dense_core(comp, adj, min_size, min_density)
        if core is not None:
            clusters.append(_build_cluster(core, notes, idf, adj))

    return sorted(clusters, key=lambda c: (-len(c.members), c.members[0].rel))
