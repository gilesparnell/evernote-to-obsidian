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

# Provenance sentinels for the `classified_by` field.
#
# granolaSync's export_granola.py stamps every note it writes with hardcoded
# placeholders (always type=meeting, always context=work). Those four required
# fields being present used to make is_classified() return True, so the LM
# classifier never revisited them — permanently freezing notes like "Bed Linen
# for the Family" as work meetings. Marking them PROVISIONAL keeps them in the
# queue until the classifier has had a look.
#
# Anything else — including the field being absent, which is the case for every
# note written before this existed — counts as settled. That default is
# load-bearing: treating absence as unclassified would re-queue the whole
# corpus.
PROVISIONAL_PROVENANCE = "export"
CLASSIFIER_PROVENANCE = "classifier"


def _split(text: str) -> tuple[dict[str, Any], str]:
    """Return (frontmatter dict, body). Empty dict if no frontmatter block."""
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return {}, text
    try:
        parsed = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError:
        # Malformed YAML (e.g. unquoted Evernote-export titles like
        # `title: 1-1: Stefan`). Treat as no frontmatter so the pipeline
        # routes the note through the normal cascade instead of crashing.
        return {}, text
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
        # Block style ALWAYS. `None` here lets PyYAML collapse a mapping with
        # no nested collections onto a single `{k: v, ...}` line — which is
        # exactly the shape of a Granola export's frontmatter. Still valid
        # YAML, but unreadable in the editor and useless in a diff.
        default_flow_style=False,
        allow_unicode=True,
    )
    if not body.startswith("\n"):
        body = "\n" + body  # keep a blank line between fm and body

    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(f"---\n{yaml_block}---\n{body}", encoding="utf-8")
    tmp.replace(path)


def is_classified(path: Path) -> bool:
    fm = read_frontmatter(path)
    if not all(fm.get(field) for field in _REQUIRED_FIELDS):
        return False
    return fm.get("classified_by") != PROVISIONAL_PROVENANCE
