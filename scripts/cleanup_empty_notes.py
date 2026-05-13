"""
Remove empty notes (no body content after frontmatter) from a Yarle-converted vault.

Usage:
    python scripts/cleanup_empty_notes.py --vault <path> [--dry-run]
"""

import argparse
import re
import sys
from pathlib import Path

_FRONTMATTER_RE = re.compile(r"^---\n.*?\n---\n?", re.DOTALL)


def is_empty_note(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    body = _FRONTMATTER_RE.sub("", text).strip()
    return not body


def find_empty_notes(vault_dir: Path) -> list[Path]:
    return [p for p in vault_dir.rglob("*.md") if is_empty_note(p)]


def cleanup_empty_notes(vault_dir: Path, dry_run: bool = False) -> dict:
    all_notes = list(vault_dir.rglob("*.md"))
    empty = [p for p in all_notes if is_empty_note(p)]

    if dry_run:
        return {"scanned": len(all_notes), "deleted": 0, "would_delete": len(empty)}

    for p in empty:
        p.unlink()

    return {"scanned": len(all_notes), "deleted": len(empty), "would_delete": 0}


def main():
    parser = argparse.ArgumentParser(description="Remove empty notes from a converted Obsidian vault")
    parser.add_argument("--vault", required=True, help="Path to the vault directory")
    parser.add_argument("--dry-run", action="store_true", help="Report without deleting")
    args = parser.parse_args()

    vault = Path(args.vault)
    if not vault.exists():
        print(f"Error: directory not found: {vault}", file=sys.stderr)
        sys.exit(1)

    result = cleanup_empty_notes(vault, dry_run=args.dry_run)

    action = "Would delete" if args.dry_run else "Deleted"
    count = result["would_delete"] if args.dry_run else result["deleted"]
    print(f"Scanned:  {result['scanned']} notes")
    print(f"{action}: {count} empty notes")


if __name__ == "__main__":
    main()
