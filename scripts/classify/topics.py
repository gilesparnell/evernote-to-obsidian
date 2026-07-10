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


_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")


def slugify(s: str) -> str:
    folded = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    folded = folded.lower().replace("'", "")
    return _NON_ALNUM_RE.sub("-", folded).strip("-")


def load_topics(vault: Path) -> list[Topic]:
    topics_dir = vault / "wiki" / "topics"
    if not topics_dir.exists():
        return []

    topics: list[Topic] = []
    for path in sorted(topics_dir.glob("*.md")):
        fm = _read_topic_frontmatter(path)
        if fm.get("type") != "topic":
            continue

        slug = fm.get("slug")
        if slug != path.stem:
            raise ValueError(
                f"{path.name}: slug {slug!r} must match filename stem {path.stem!r}"
            )

        aliases = fm.get("aliases", [])
        if not isinstance(aliases, list):
            raise ValueError(f"{path.name}: aliases must be a list")
        if not all(isinstance(alias, str) for alias in aliases):
            raise ValueError(f"{path.name}: aliases must be a list of strings")

        exclude = fm.get("exclude", [])
        if not isinstance(exclude, list):
            raise ValueError(f"{path.name}: exclude must be a list of glob patterns")
        if not all(isinstance(pat, str) for pat in exclude):
            raise ValueError(f"{path.name}: exclude must be a list of strings")

        status = fm.get("status", "active")
        if status == "paused":
            continue

        topics.append(
            Topic(slug=slug, aliases=aliases, status=status, path=path, exclude=exclude)
        )

    validate(topics)
    return topics


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
