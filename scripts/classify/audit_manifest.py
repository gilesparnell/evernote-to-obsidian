"""Format the classifier's deletion manifest into a human-readable report.

After every classifier chunk that purged files, the operator audits
.classify_deleted_manifest.json to confirm nothing important was hard-
deleted. This CLI replaces the ad-hoc heredoc python that operators kept
hitting copy-paste issues with (leading-whitespace indent errors, shell
heredoc-delimiter-must-be-column-0 surprises).

Default behaviour: show only the most recent run's deletions — that's
what the post-chunk operator checklist always wants. Pass --all-runs to
see every run.

Usage:
    # Just this run's deletions (default)
    scripts/classify/venv/bin/python scripts/classify/audit_manifest.py \\
        --vault ~/Documents/ObsidianVault/Personal

    # Every deletion across all runs
    scripts/classify/venv/bin/python scripts/classify/audit_manifest.py \\
        --vault ~/Documents/ObsidianVault/Personal --all-runs

    # Cap output (useful when the manifest grows large)
    scripts/classify/venv/bin/python scripts/classify/audit_manifest.py \\
        --vault ~/Documents/ObsidianVault/Personal --limit 20
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

# Allow direct script invocation in addition to `python -m`.
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_MANIFEST_FILENAME = ".classify_deleted_manifest.json"
_FILENAME_DISPLAY_WIDTH = 55


def load_manifest(vault: Path) -> dict[str, Any] | None:
    """Read the deletion manifest from ``<vault>/.classify_deleted_manifest.json``.

    Returns the parsed JSON dict (shape: ``{"deleted": [...]}`` ), or None
    when the file doesn't exist. Raises ``json.JSONDecodeError`` on corrupt
    JSON so the operator sees the problem rather than getting silent zeros.
    """
    target = vault / _MANIFEST_FILENAME
    if not target.exists():
        return None
    return json.loads(target.read_text(encoding="utf-8"))


def latest_run_id(deleted: list[dict[str, Any]]) -> str | None:
    """Return the highest ISO-8601 run_id in the deletion list, or None
    when the list is empty. ISO timestamps sort lexicographically, so
    ``max()`` over the strings gives the most recent run."""
    if not deleted:
        return None
    return max(e["run_id"] for e in deleted)


def entries_for_run(
    deleted: list[dict[str, Any]], run_id: str,
) -> list[dict[str, Any]]:
    """Return the subset of ``deleted`` whose run_id matches, preserving
    order (manifest is append-only, so order = deletion sequence)."""
    return [e for e in deleted if e["run_id"] == run_id]


def format_entry(index: int, entry: dict[str, Any]) -> str:
    """Render a single deletion as a one-line report row:

        123. [11 chars] Note.13.md                                              | Bread rolls

    The index is right-padded to 4 columns (handles up to 9999 entries
    aligned). The filename is truncated to 55 chars so the report stays
    columnar in a standard terminal."""
    basename = entry["path"].rsplit("/", 1)[-1]
    if len(basename) > _FILENAME_DISPLAY_WIDTH:
        basename = basename[: _FILENAME_DISPLAY_WIDTH - 1] + "…"
    return (
        f"  {index:>4}. [{entry['stripped_body_chars']:>2} chars] "
        f"{basename:<{_FILENAME_DISPLAY_WIDTH}} | {entry['body_preview']}"
    )


def audit(
    vault: Path, last_run_only: bool, limit: int | None,
) -> str:
    """Build the full report string. Returns it rather than printing so
    tests can assert against the rendered output cleanly."""
    data = load_manifest(vault)
    if data is None:
        return (
            f"no manifest at {vault / _MANIFEST_FILENAME} — "
            f"either no chunks have purged anything yet, or you're "
            f"pointing at the wrong vault."
        )

    deleted = data.get("deleted", [])
    if not deleted:
        return "manifest exists but no deletions recorded (0 purged)."

    if last_run_only:
        latest = latest_run_id(deleted)
        rows = entries_for_run(deleted, latest)
        header = (
            f"This run ({latest}): {len(rows)} purged "
            f"(of {len(deleted)} total across all runs)\n"
        )
    else:
        rows = deleted
        per_run: dict[str, int] = {}
        for e in rows:
            per_run[e["run_id"]] = per_run.get(e["run_id"], 0) + 1
        breakdown = "\n".join(
            f"  {rid}: {count}" for rid, count in sorted(per_run.items())
        )
        header = (
            f"All runs: {len(rows)} purged across {len(per_run)} runs\n"
            f"{breakdown}\n"
        )

    if limit is not None:
        rows = rows[:limit]

    body_lines = [format_entry(i, e) for i, e in enumerate(rows, 1)]
    return header + "\n" + "\n".join(body_lines)


_CLI_DESCRIPTION = """\
Audit the classifier's deletion manifest. Defaults to showing only the
most recent run's deletions (what the post-chunk operator checklist
wants). Use --all-runs for the full history.
"""

_CLI_EPILOG = """\
Common patterns:

  # Audit the most recent chunk's deletions
  %(prog)s --vault ~/Documents/ObsidianVault/Personal

  # See every deletion across every run
  %(prog)s --vault ~/Documents/ObsidianVault/Personal --all-runs

  # Cap output to first 20 (sample when the manifest is huge)
  %(prog)s --vault ~/Documents/ObsidianVault/Personal --limit 20
"""


def main() -> None:
    parser = argparse.ArgumentParser(
        description=_CLI_DESCRIPTION,
        epilog=_CLI_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--vault", required=True, type=Path,
        help="Obsidian vault root (e.g. ~/Documents/ObsidianVault/Personal).",
    )
    parser.add_argument(
        "--all-runs", action="store_true",
        help="Show every deletion across every run. Default is last run only.",
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Cap output to the first N entries (useful when the manifest "
             "is large and you only need a sample).",
    )
    args = parser.parse_args()

    report = audit(
        vault=args.vault,
        last_run_only=not args.all_runs,
        limit=args.limit,
    )
    print(report)


if __name__ == "__main__":
    main()
