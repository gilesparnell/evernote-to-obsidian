"""Vault migration tool — move classified Evernote notes to the right vault.

Two passes in one run:
- **Cross-vault:** notes with ``context: work`` move from
  ``Personal/Evernote/...`` to ``Business/`` (flat root, no subfolders).
- **Intra-vault defrag:** notes with ``context: personal`` or ``education``
  move from ``Personal/Evernote/...`` to ``Personal/`` (flat root).

End state: zero ``Evernote/`` subfolders in either vault. If the Evernote
directory ends up empty, it is deleted.

Safety:
- **--dry-run by default.** Must pass ``--confirm`` to write.
- Only classified notes are moved (``is_classified()`` must return True).
- Filename collisions get ``_2``, ``_3``, ... suffixes — never overwrite.
- All moves are appended to ``migration-log.md`` at the Business vault
  root for traceability.

Usage:
    scripts/classify/venv/bin/python scripts/classify/migrate_vault.py \\
        --personal ~/Documents/ObsidianVault/Personal \\
        --business ~/Documents/ObsidianVault/Business \\
        --confirm
"""

from __future__ import annotations

import argparse
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

# Allow direct script invocation in addition to `python -m`.
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.classify import frontmatter as _fm

EVERNOTE_SUBDIR = "Evernote"
_WORK_CONTEXTS = frozenset({"work"})
_PERSONAL_CONTEXTS = frozenset({"personal", "education"})
MIGRATION_LOG_FILENAME = "migration-log.md"


def _resolve_destination(dest_dir: Path, filename: str) -> Path:
    """Return a unique destination path. If `filename` already exists in
    dest_dir, append `_2`, `_3`, ... until a free slot is found."""
    candidate = dest_dir / filename
    if not candidate.exists():
        return candidate
    stem, suffix = candidate.stem, candidate.suffix
    n = 2
    while True:
        candidate = dest_dir / f"{stem}_{n}{suffix}"
        if not candidate.exists():
            return candidate
        n += 1


def _append_migration_log(business: Path, operations: list[tuple[Path, Path, str]]) -> None:
    log_path = business / MIGRATION_LOG_FILENAME
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    parts: list[str] = []
    if log_path.exists():
        parts.append(log_path.read_text(encoding="utf-8").rstrip())
        parts.append("")
    parts.append(f"## {timestamp} — migrate_vault run")
    parts.append("")
    for src, dest, how in operations:
        parts.append(f"- `{src}` → `{dest}` ({how})")
    parts.append("")
    log_path.write_text("\n".join(parts), encoding="utf-8")


def migrate_vault(
    personal: Path,
    business: Path,
    dry_run: bool = True,
    limit: int | None = None,
) -> dict[str, Any]:
    """Move classified Evernote notes out of `personal/Evernote/`.

    Returns a summary dict with counts and the operation log.
    """
    evernote_root = personal / EVERNOTE_SUBDIR
    operations: list[tuple[Path, Path, str]] = []
    to_business = 0
    to_personal_root = 0
    skipped_unclassified = 0

    if evernote_root.exists():
        for md_path in sorted(evernote_root.rglob("*.md")):
            if limit is not None and (to_business + to_personal_root) >= limit:
                break

            if not _fm.is_classified(md_path):
                skipped_unclassified += 1
                continue

            context = _fm.read_frontmatter(md_path).get("context")
            if context in _WORK_CONTEXTS:
                destination = _resolve_destination(business, md_path.name)
                how = "work → Business root"
                to_business += 1
            elif context in _PERSONAL_CONTEXTS:
                destination = _resolve_destination(personal, md_path.name)
                how = "personal → Personal root"
                to_personal_root += 1
            else:
                # Classified but with an unexpected context value — skip
                # rather than risk a wrong-vault move.
                skipped_unclassified += 1
                continue

            operations.append((md_path, destination, how))
            if not dry_run:
                shutil.move(str(md_path), str(destination))

    # Clean up: delete Evernote/ if it ended up empty.
    if not dry_run and evernote_root.exists():
        if not any(evernote_root.rglob("*.md")):
            shutil.rmtree(evernote_root)

    if not dry_run and operations:
        _append_migration_log(business, operations)

    return {
        "to_business": to_business,
        "to_personal_root": to_personal_root,
        "skipped_unclassified": skipped_unclassified,
        "dry_run": dry_run,
        "operations": [(str(s), str(d), how) for s, d, how in operations],
    }


_CLI_DESCRIPTION = """\
Move classified Evernote-imported notes out of Personal/Evernote/ subfolders
to the right vault root: context=work to Business/, context=personal or
education to Personal/. End state: zero Evernote/ subfolders.

Unclassified notes are skipped with a warning - run classify_vault first.
Filename collisions get _2, _3 suffixes; nothing is ever overwritten.
"""

_CLI_EPILOG = """\
Common patterns:

  # Preview only - see counts, no moves (default)
  %(prog)s --personal ~/Documents/ObsidianVault/Personal \\
    --business ~/Documents/ObsidianVault/Business

  # Apply migration after classify + sampling have validated quality
  %(prog)s --personal ~/Documents/ObsidianVault/Personal \\
    --business ~/Documents/ObsidianVault/Business --confirm

  # Staged rollout - first 100 notes only
  %(prog)s --personal ... --business ... --confirm --limit 100
"""


def main() -> None:
    parser = argparse.ArgumentParser(
        description=_CLI_DESCRIPTION,
        epilog=_CLI_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--personal", required=True, type=Path,
        help="Personal vault root (source of work/personal notes to migrate).",
    )
    parser.add_argument(
        "--business", required=True, type=Path,
        help="Business vault root (destination for work-context notes).",
    )
    parser.add_argument(
        "--confirm", action="store_true",
        help="Apply moves. Default is a count-only dry run.",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Force dry run even if --confirm is also passed. Wins on conflict.",
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Cap the number of notes moved this run (default: no cap).",
    )
    args = parser.parse_args()

    # --dry-run wins over --confirm if both are passed.
    dry_run = args.dry_run or not args.confirm

    summary = migrate_vault(
        personal=args.personal,
        business=args.business,
        dry_run=dry_run,
        limit=args.limit,
    )
    mode = "DRY RUN" if dry_run else "APPLIED"
    print(
        f"{mode}: to_business={summary['to_business']}, "
        f"to_personal_root={summary['to_personal_root']}, "
        f"skipped_unclassified={summary['skipped_unclassified']}"
    )


if __name__ == "__main__":
    main()
