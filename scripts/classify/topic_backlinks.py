"""Reconcile source-note ``topics:`` backlinks from topic collector caches."""

from __future__ import annotations

import json
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

# Allow direct script invocation from future orchestrator/panel entry points.
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.classify.collect_topic import (
    _iter_source_notes,
    collect_topic,
    topic_cache_path,
)
from scripts.classify.topics import Topic


_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_WIKILINK_RE = re.compile(r"^\[\[([^\]]+)]]$")
_WRITE_SLEEP_SECONDS = 0.05


class _FrontmatterDumper(yaml.SafeDumper):
    """Match `frontmatter.write_frontmatter`'s plain style exactly.

    No forced quoting: PyYAML already quotes only where YAML requires it
    (e.g. `'[[slug]]'` wikilinks, which would otherwise parse as nested
    flow sequences). A previous forced `style='"'` representer re-quoted
    every key and value, churning untouched frontmatter across the vault.
    """

    def increase_indent(self, flow: bool = False, indentless: bool = False):
        return super().increase_indent(flow, False)


@dataclass(frozen=True)
class BacklinkSummary:
    updated: int = 0
    removed: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class _ParsedNote:
    frontmatter: dict[str, Any]
    body: str
    has_frontmatter: bool


def reconcile_backlinks(
    *,
    vault: Path,
    topics: list[Topic],
    json_out: Path,
    dry_run: bool = False,
) -> BacklinkSummary:
    """Apply managed topic wikilinks to source-note frontmatter."""
    registered_slugs = {topic.slug for topic in topics}
    desired_by_note = _desired_backlinks(vault=vault, topics=topics, json_out=json_out)

    updated = 0
    removed = 0
    skipped = 0
    errors: list[str] = []

    for path in _iter_source_notes(vault):
        rel = path.relative_to(vault).as_posix()
        try:
            parsed = _parse_note(path)
        except ValueError as exc:
            skipped += 1
            errors.append(f"{rel}: {exc}")
            continue

        current = parsed.frontmatter.get("topics", [])
        if current is None:
            current = []
        if not isinstance(current, list):
            skipped += 1
            errors.append(f"{rel}: topics must be a list")
            continue

        current_links = [item for item in current if isinstance(item, str)]
        desired_slugs = desired_by_note.get(rel, set())
        next_links = _reconciled_links(
            current_links=current_links,
            desired_slugs=desired_slugs,
            registered_slugs=registered_slugs,
        )
        if next_links == current_links:
            continue

        removed += _removed_managed_count(
            current_links=current_links,
            next_links=next_links,
            registered_slugs=registered_slugs,
        )
        updated += 1

        if dry_run:
            continue

        if next_links:
            _write_frontmatter_fields(path, parsed=parsed, fields={"topics": next_links})
        else:
            _write_frontmatter_without_key(path, parsed=parsed, key="topics")
        time.sleep(_WRITE_SLEEP_SECONDS)

    return BacklinkSummary(
        updated=updated,
        removed=removed,
        skipped=skipped,
        errors=errors,
    )


def _desired_backlinks(
    *, vault: Path, topics: list[Topic], json_out: Path
) -> dict[str, set[str]]:
    desired: dict[str, set[str]] = {}
    for topic in topics:
        cache_path = topic_cache_path(vault=vault, slug=topic.slug, json_out=json_out)
        if not cache_path.exists():
            cache_path = collect_topic(vault=vault, topic=topic, json_out=json_out)

        data = json.loads(cache_path.read_text(encoding="utf-8"))
        for source in data.get("sources", []):
            rel = source.get("path")
            if isinstance(rel, str):
                desired.setdefault(rel, set()).add(topic.slug)
    return desired


def _reconciled_links(
    *,
    current_links: list[str],
    desired_slugs: set[str],
    registered_slugs: set[str],
) -> list[str]:
    hand_written = [
        link
        for link in current_links
        if (slug := _slug_from_wikilink(link)) is None or slug not in registered_slugs
    ]
    managed = [f"[[{slug}]]" for slug in sorted(desired_slugs)]
    return hand_written + managed


def _removed_managed_count(
    *,
    current_links: list[str],
    next_links: list[str],
    registered_slugs: set[str],
) -> int:
    next_set = set(next_links)
    return sum(
        1
        for link in current_links
        if link not in next_set
        and (slug := _slug_from_wikilink(link)) is not None
        and slug in registered_slugs
    )


def _slug_from_wikilink(value: str) -> str | None:
    match = _WIKILINK_RE.match(value)
    if not match:
        return None
    return match.group(1)


def _parse_note(path: Path) -> _ParsedNote:
    text = path.read_text(encoding="utf-8")
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return _ParsedNote(frontmatter={}, body=text, has_frontmatter=False)

    try:
        parsed = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError as exc:
        raise ValueError("invalid YAML frontmatter") from exc
    if not isinstance(parsed, dict):
        raise ValueError("frontmatter must be a mapping")
    return _ParsedNote(
        frontmatter=parsed,
        body=text[match.end():],
        has_frontmatter=True,
    )


def _write_frontmatter_without_key(
    path: Path, *, parsed: _ParsedNote, key: str
) -> None:
    fm = dict(parsed.frontmatter)
    fm.pop(key, None)
    _write_frontmatter(path, frontmatter=fm, body=parsed.body, keep_block=parsed.has_frontmatter)


def _write_frontmatter_fields(
    path: Path, *, parsed: _ParsedNote, fields: dict[str, Any]
) -> None:
    fm = dict(parsed.frontmatter)
    fm.update(fields)
    _write_frontmatter(path, frontmatter=fm, body=parsed.body, keep_block=True)


def _write_frontmatter(
    path: Path, *, frontmatter: dict[str, Any], body: str, keep_block: bool
) -> None:
    tmp = path.with_name(path.name + ".tmp")
    if frontmatter or keep_block:
        yaml_block = yaml.dump(
            frontmatter,
            Dumper=_FrontmatterDumper,
            sort_keys=False,
            default_flow_style=None,
            allow_unicode=True,
        )
        if not body.startswith("\n"):
            body = "\n" + body
        tmp.write_text(f"---\n{yaml_block}---\n{body}", encoding="utf-8")
    else:
        tmp.write_text(body, encoding="utf-8")
    tmp.replace(path)
