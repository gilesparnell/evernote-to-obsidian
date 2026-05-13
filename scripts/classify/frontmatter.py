"""Frontmatter read/write/is_classified for Obsidian markdown notes.

Public API:
    read_frontmatter(path)              -> dict   (empty if no frontmatter)
    write_frontmatter(path, new_fields) -> None   (atomic via .tmp + rename)
    is_classified(path)                 -> bool   (R2 required fields present)

The required R2 fields for is_classified are type, org, context, up.
people, project, and tags are optional — their absence does NOT make a
note unclassified.

Writes are atomic: the new content is written to a sibling .tmp file and
then renamed over the original. This avoids partial writes on iCloud-synced
volumes if the process is interrupted mid-write.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_REQUIRED_FIELDS = ("type", "org", "context", "up")


def _split(text: str) -> tuple[dict[str, Any], str]:
    """Return (frontmatter dict, body). Empty dict if no frontmatter block."""
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return {}, text
    parsed = yaml.safe_load(match.group(1)) or {}
    if not isinstance(parsed, dict):
        # YAML block parsed to a non-dict (scalar, list) — refuse rather
        # than guess. Caller treats this as no frontmatter.
        return {}, text
    return parsed, text[match.end():]


def read_frontmatter(path: Path) -> dict[str, Any]:
    fm, _ = _split(path.read_text(encoding="utf-8"))
    return fm


def write_frontmatter(path: Path, new_fields: dict[str, Any]) -> None:
    fm, body = _split(path.read_text(encoding="utf-8"))
    fm.update(new_fields)  # new wins on collision; existing keys keep position

    yaml_block = yaml.safe_dump(
        fm,
        sort_keys=False,
        default_flow_style=None,
        allow_unicode=True,
    )
    if not body.startswith("\n"):
        body = "\n" + body  # keep a blank line between fm and body

    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(f"---\n{yaml_block}---\n{body}", encoding="utf-8")
    tmp.replace(path)


def is_classified(path: Path) -> bool:
    fm = read_frontmatter(path)
    return all(fm.get(field) for field in _REQUIRED_FIELDS)
