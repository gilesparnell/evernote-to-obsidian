"""Build and write the generated Home dashboard section."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

# Allow direct script invocation from future orchestrator/panel entry points.
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.classify.gardener import review_queue_count, topic_freshness
from scripts.classify.wiki_io import (
    GENERATED_END,
    GENERATED_START,
    _atomic_write,
    replace_generated_region,
)


_HEALTH_RE = re.compile(r"^Health score: (\d+)/100$")


def build_home_section(*, vault: Path, json_out: Path, run_state: dict) -> str:
    """Return the generated markdown body for Home.md."""
    del run_state

    rows = topic_freshness(vault=vault, json_out=json_out)
    parts = [
        "## Topics & synthesis",
        "",
        *_topic_lines(rows),
    ]
    status = _status_line(vault)
    if status:
        parts.extend(["", status])
    return "\n".join(parts).rstrip() + "\n"


def write_home(*, vault: Path, section_md: str, dry_run: bool) -> None:
    """Write vault/Home.md, replacing only the generated region."""
    path = vault / "Home.md"
    existing = path.read_text(encoding="utf-8") if path.exists() else _empty_home()
    updated = replace_generated_region(existing, section_md)

    if dry_run:
        return

    _atomic_write(path, updated)


def _topic_lines(rows: list[Any]) -> list[str]:
    if not rows:
        return ["No topics registered yet."]
    return [
        "| Topic | Sources | Last synthesis | Changed |",
        "|---|---:|---|---|",
        *[_topic_row(row) for row in rows],
    ]


def _topic_row(row: Any) -> str:
    return (
        f"| {row.slug} | {_display(row.source_count)} | "
        f"{_display(row.last_synthesis)} | {_display_hash_changed(row.hash_changed)} |"
    )


def _status_line(vault: Path) -> str:
    parts: list[str] = []
    gardener = vault / "wiki" / "gardener.md"
    if gardener.exists():
        health = _read_health_score(gardener)
        if health is not None:
            parts.append(f"Health {health}/100")
        parts.append("[Gardener report](wiki/gardener.md)")

    if (vault / "wiki" / "index.md").exists():
        parts.append("[Wiki index](wiki/index.md)")

    if (vault / "classification-review.md").exists():
        parts.append(f"Review queue: {review_queue_count(vault)}")

    return " · ".join(parts)


def _read_health_score(path: Path) -> int | None:
    for line in path.read_text(encoding="utf-8").splitlines():
        match = _HEALTH_RE.match(line.strip())
        if match:
            return int(match.group(1))
    return None


def _empty_home() -> str:
    return (
        "---\n"
        "type: dashboard\n"
        "---\n\n"
        "# Home\n\n"
        f"{GENERATED_START}\n"
        f"{GENERATED_END}\n"
    )


def _display(value: Any) -> str:
    if value is None or value == "":
        return "n/a"
    return str(value).replace("\n", " ")


def _display_hash_changed(value: bool | None) -> str:
    if value is True:
        return "yes"
    if value is False:
        return "no"
    return "n/a"
