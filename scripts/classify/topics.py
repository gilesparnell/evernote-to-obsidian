"""Topic stub discovery for synthesis.

Topic stubs live at ``wiki/topics/<slug>.md`` and carry frontmatter that
declares the canonical topic slug plus aliases used by later collector tasks.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import yaml

from scripts.classify.frontmatter import read_frontmatter


@dataclass(frozen=True)
class Topic:
    slug: str
    aliases: list[str]
    status: str
    path: Path
    exclude: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class QuarantinedTopic:
    """A topic file that could not be loaded (bad shape or a collision).

    Recorded and surfaced in the gardener report rather than raised — a single
    malformed or colliding stub must never brick the vault's nightly chain.
    """

    path: Path
    reason: str


@dataclass(frozen=True)
class TopicLoad:
    topics: list[Topic]
    quarantined: list[QuarantinedTopic]


# Statuses that keep the file on disc but take the topic out of the active set:
# `paused` is a temporary hold, `rejected` is the tombstone left by the reject
# ritual (see load_rejected_slugs).
_INACTIVE_STATUSES = frozenset({"paused", "rejected"})
_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")


def slugify(s: str) -> str:
    folded = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    folded = folded.lower().replace("'", "")
    return _NON_ALNUM_RE.sub("-", folded).strip("-")


def load_topics(vault: Path) -> list[Topic]:
    """Return the loadable topics for a vault (fail-soft — bad files skipped)."""
    return load_topic_report(vault).topics


def load_topic_report(vault: Path) -> TopicLoad:
    """Load topic stubs, quarantining any that are malformed or collide.

    A single bad stub (bad shape, invalid YAML, slug/alias collision) is
    recorded in ``quarantined`` and skipped rather than raised — otherwise one
    file would break ``load_topics`` for every synthesis step, every night,
    until a human intervened. ``validate`` remains the strict primitive for
    callers (e.g. the topic proposer) that need to reject a set outright.
    """
    topics_dir = vault / "wiki" / "topics"
    if not topics_dir.exists():
        return TopicLoad(topics=[], quarantined=[])

    topics: list[Topic] = []
    quarantined: list[QuarantinedTopic] = []
    seen_slugs: set[str] = set()
    alias_owner: dict[str, str] = {}  # casefolded alias -> owning slug

    for path in sorted(topics_dir.glob("*.md")):
        topic, reason = _parse_topic(path)
        if reason is not None:
            quarantined.append(QuarantinedTopic(path=path, reason=reason))
            continue
        if topic is None:
            continue  # not a topic file, or paused — silently skipped

        collision = _collision_reason(topic, seen_slugs, alias_owner)
        if collision is not None:
            quarantined.append(QuarantinedTopic(path=path, reason=collision))
            continue

        seen_slugs.add(topic.slug)
        for alias in topic.aliases:
            alias_owner[alias.casefold()] = topic.slug
        topics.append(topic)

    return TopicLoad(topics=topics, quarantined=quarantined)


def load_rejected_slugs(vault: Path) -> set[str]:
    """Slugs the operator has tombstoned with ``status: rejected``.

    The tombstone file stays on disc deliberately: a raw delete would leave
    every ``topics: [[slug]]`` backlink dangling, and clicking one in Obsidian
    creates an empty note (the "zeroed notes" incident). Keeping the file means
    the link still resolves, and this set is how the proposer remembers never to
    re-create or re-propose the topic.
    """
    topics_dir = vault / "wiki" / "topics"
    if not topics_dir.exists():
        return set()

    rejected: set[str] = set()
    for path in sorted(topics_dir.glob("*.md")):
        try:
            fm = _read_topic_frontmatter(path)
        except ValueError:
            continue  # malformed files are the quarantine path's problem
        if fm.get("type") != "topic" or fm.get("status") != "rejected":
            continue
        slug = fm.get("slug")
        rejected.add(slug if isinstance(slug, str) and slug else path.stem)
    return rejected


def _parse_topic(path: Path) -> tuple[Topic | None, str | None]:
    """Parse one topic file. Returns (topic, None) on success, (None, None) to
    skip (not a topic / paused), or (None, reason) to quarantine."""
    try:
        fm = _read_topic_frontmatter(path)
    except ValueError as exc:
        # _read_topic_frontmatter raises with the "…: invalid YAML…" message.
        return None, str(exc).split(": ", 1)[-1]

    if fm.get("type") != "topic":
        return None, None

    slug = fm.get("slug")
    if slug != path.stem:
        return None, f"slug {slug!r} must match filename stem {path.stem!r}"

    aliases = fm.get("aliases", [])
    if not isinstance(aliases, list):
        return None, "aliases must be a list"
    if not all(isinstance(alias, str) for alias in aliases):
        return None, "aliases must be a list of strings"

    exclude = fm.get("exclude", [])
    if not isinstance(exclude, list):
        return None, "exclude must be a list of glob patterns"
    if not all(isinstance(pat, str) for pat in exclude):
        return None, "exclude must be a list of strings"

    status = fm.get("status", "active")
    if status in _INACTIVE_STATUSES:
        return None, None

    return (
        Topic(slug=slug, aliases=aliases, status=status, path=path, exclude=exclude),
        None,
    )


def _collision_reason(
    topic: Topic, seen_slugs: set[str], alias_owner: dict[str, str]
) -> str | None:
    if topic.slug in seen_slugs:
        return f"slug collision: {topic.slug}"
    for alias in topic.aliases:
        owner = alias_owner.get(alias.casefold())
        if owner is not None and owner != topic.slug:
            return f"alias overlap: {alias!r} already used by {owner!r}"
    return None


def validate(topics: Iterable[Topic]) -> None:
    seen_slugs: set[str] = set()
    alias_owner: dict[str, Topic] = {}
    alias_text: dict[str, str] = {}

    for topic in topics:
        if topic.slug in seen_slugs:
            raise ValueError(f"slug collision: {topic.slug}")
        seen_slugs.add(topic.slug)

        for alias in topic.aliases:
            key = alias.casefold()
            owner = alias_owner.get(key)
            if owner is not None and owner.slug != topic.slug:
                raise ValueError(
                    f"alias overlap: {alias_text[key]!r} appears in "
                    f"{owner.slug!r} and {topic.slug!r}"
                )
            alias_owner[key] = topic
            alias_text[key] = alias


def _read_topic_frontmatter(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    match = _FRONTMATTER_RE.match(text)
    if match:
        try:
            yaml.safe_load(match.group(1))
        except yaml.YAMLError as exc:
            raise ValueError(f"{path.name}: invalid YAML frontmatter") from exc

    return read_frontmatter(path)
