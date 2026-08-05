"""Pre-flight sweep of iCloud conflict copies / dataless placeholders.

Runs before any ``load_topics`` in the nightly chain. iCloud can drop files
into ``wiki/topics/`` that never came from our writer — a numbered conflict
copy (``slug 2.md``), a "(conflicted copy)" file, or a dataless
``.slug.md.icloud`` placeholder. Left in place they reach the reader as bogus
topic stubs. This moves them into ``wiki/topics/_quarantine/`` (which
``load_topics`` never globs and ``collect`` never ingests) so they are isolated
and visible, not silently poisoning the chain.
"""

from __future__ import annotations

import re
from pathlib import Path

_QUARANTINE_DIRNAME = "_quarantine"
# iCloud numbered conflict copy: "Foo 2.md", "Foo 10.md". Legitimate topic
# stubs are slugified (hyphens, no spaces), so a space before the extension is
# never one of ours.
_NUMBERED_CONFLICT_RE = re.compile(r" \d+\.md$")


def _is_conflict(name: str) -> bool:
    if name.endswith(".icloud"):
        return True
    if "conflicted copy" in name.lower():
        return True
    return bool(_NUMBERED_CONFLICT_RE.search(name))


def sweep_topic_conflicts(vault: Path) -> list[Path]:
    """Move conflict copies / placeholders out of ``wiki/topics/``.

    Returns the original paths that were moved (for the gardener report).
    Non-recursive: files already inside ``_quarantine/`` are left alone.
    """
    topics_dir = vault / "wiki" / "topics"
    if not topics_dir.exists():
        return []

    quarantine = topics_dir / _QUARANTINE_DIRNAME
    moved: list[Path] = []
    for entry in sorted(topics_dir.iterdir()):
        if entry.is_dir():
            continue
        if not _is_conflict(entry.name):
            continue
        quarantine.mkdir(exist_ok=True)
        target = quarantine / entry.name
        if target.exists():  # never clobber a prior quarantine
            target = quarantine / f"{entry.stem}.{len(moved)}{entry.suffix}"
        entry.rename(target)
        moved.append(entry)
    return moved
