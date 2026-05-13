"""Legacy `up:` rewriter — repoint pre-Unit-7 Granola notes to the new MOC.

The original Granola export wrote `up: "[[Meetings Homepage]]"`. Unit 7
renames that MOC to `Meetings.md` (short, single-word) for the universal
graph view. This script walks a vault and rewrites every legacy reference
in place via atomic .tmp + rename so iCloud-interrupted writes don't
corrupt notes.

Usage:
    # Dry run — count files that would change, no writes
    scripts/classify/venv/bin/python scripts/classify/migrate_legacy_up.py \\
        --vault ~/Documents/ObsidianVault/Personal

    # Apply (after reviewing the dry-run count)
    scripts/classify/venv/bin/python scripts/classify/migrate_legacy_up.py \\
        --vault ~/Documents/ObsidianVault/Personal --confirm
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Any

_LEGACY_RE = re.compile(r'up:\s*"\[\[Meetings Homepage\]\]"')
_NEW_VALUE = 'up: "[[Meetings]]"'


def migrate(root: Path, dry_run: bool = True) -> dict[str, Any]:
    """Walk ``root`` rewriting legacy ``up:`` links. Skips hidden dirs.

    Returns a summary dict: {"rewrites": int, "skipped": int, "dry_run": bool}.
    """
    rewrites = 0
    skipped = 0
    for path in sorted(root.rglob("*.md")):
        rel_parts = path.relative_to(root).parts
        if any(part.startswith(".") for part in rel_parts):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            skipped += 1
            continue
        if not _LEGACY_RE.search(text):
            continue

        new_text = _LEGACY_RE.sub(_NEW_VALUE, text)
        if not dry_run:
            tmp = path.with_name(path.name + ".tmp")
            tmp.write_text(new_text, encoding="utf-8")
            tmp.replace(path)
        rewrites += 1

    return {"rewrites": rewrites, "skipped": skipped, "dry_run": dry_run}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--vault", required=True, type=Path,
                        help="Vault root to scan recursively.")
    parser.add_argument("--confirm", action="store_true",
                        help="Apply changes (default is a count-only dry run).")
    args = parser.parse_args()

    result = migrate(args.vault, dry_run=not args.confirm)
    mode = "APPLIED" if args.confirm else "DRY RUN"
    print(f"{mode}: rewrites={result['rewrites']}, skipped={result['skipped']}")


if __name__ == "__main__":
    main()
