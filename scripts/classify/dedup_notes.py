"""Remove exact-duplicate numbered note copies left by the Yarle export.

When two Evernote notes shared a title, Yarle wrote the second as
``Title.N.md`` to avoid clobbering ``Title.md``. SOME of those numbered
copies are byte-for-byte identical to their base — true duplicates worth
removing. MANY are NOT: distinct notes that merely share a title (e.g. two
different emails in the same thread). So this tool is deliberately
conservative — it deletes a numbered copy ONLY when:

  1. its name matches ``<base>.<digits>.md``, AND
  2. the base ``<base>.md`` exists, AND
  3. the two files are byte-for-byte identical.

The base is always kept; content-differing pairs and orphaned numbered
files (no base) are left untouched for normal triage.

Safety: dry-run by default (preview). With ``--confirm`` each duplicate is
moved to ``~/.Trash/evernote-dedup-<date>/`` (recoverable in Finder) and
recorded in the shared ``.classify_deleted_manifest.json`` audit trail.

Usage:
    scripts/classify/venv/bin/python scripts/classify/dedup_notes.py \\
        --vault ~/Documents/ObsidianVault/Personal              # preview
    scripts/classify/venv/bin/python scripts/classify/dedup_notes.py \\
        --vault ~/Documents/ObsidianVault/Personal --confirm    # delete
"""

from __future__ import annotations

import argparse
import filecmp
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

# Allow direct script invocation in addition to `python -m`.
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.classify.classify_vault import (
    _append_deletion_manifest,
    _iter_md_files,
    _now_aest_iso,
    _strip_frontmatter,
)

# Matches a Yarle collision suffix: "....<digits>.md".
_NUMBERED_SUFFIX_RE = re.compile(r"\.\d+\.md$")


def _base_path_for(path: Path) -> Path | None:
    """Map ``Title.N.md`` → ``Title.md``. Returns None for a non-numbered
    name (so a base file is never itself treated as a copy)."""
    if not _NUMBERED_SUFFIX_RE.search(path.name):
        return None
    return path.with_name(_NUMBERED_SUFFIX_RE.sub(".md", path.name))


def _body_of(path: Path) -> str:
    return _strip_frontmatter(path.read_text(encoding="utf-8")).strip()


def is_exact_duplicate_copy(path: Path, *, body_only: bool = False) -> Path | None:
    """Return the base path if ``path`` is a numbered copy duplicating an
    existing base ``Title.md``; otherwise None.

    Default: byte-for-byte identity. With ``body_only=True``: identical BODY
    after frontmatter is stripped — catches Yarle copies whose classifier
    frontmatter (people/tags/type) diverged but whose content is the same."""
    base = _base_path_for(path)
    if base is None or not base.exists():
        return None
    if body_only:
        return base if _body_of(path) == _body_of(base) else None
    if filecmp.cmp(path, base, shallow=False):
        return base
    return None


def find_duplicate_copies(
    vault: Path, folder: str | None = None, *, body_only: bool = False
) -> list[tuple[Path, Path]]:
    """Walk the vault (reusing the classifier's skip-list) and return
    ``(duplicate_copy, base)`` pairs for every numbered copy that duplicates
    its base (byte-identical, or body-identical when ``body_only``)."""
    pairs: list[tuple[Path, Path]] = []
    for md_path in _iter_md_files(vault, folder):
        base = is_exact_duplicate_copy(md_path, body_only=body_only)
        if base is not None:
            pairs.append((md_path, base))
    return pairs


def _move_to_trash(path: Path, dest_dir: Path) -> Path:
    """Move ``path`` into ``dest_dir`` (created on demand), suffixing the
    name on collision so nothing in the trash is overwritten."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    target = dest_dir / path.name
    i = 1
    while target.exists():
        target = dest_dir / f"{path.stem}_{i}{path.suffix}"
        i += 1
    shutil.move(str(path), str(target))
    return target


def dedup_vault(
    vault: Path,
    folder: str | None = None,
    confirm: bool = False,
    trash_root: Path | None = None,
    *,
    body_only: bool = False,
) -> dict[str, object]:
    """Find duplicate numbered copies. With ``confirm=True``, move each to the
    trash and log it to the deletion manifest; otherwise just report. Returns a
    summary dict. ``body_only`` matches on stripped body rather than bytes."""
    trash_root = trash_root or (Path.home() / ".Trash")
    pairs = find_duplicate_copies(vault, folder, body_only=body_only)

    deleted = 0
    if confirm and pairs:
        run_id = _now_aest_iso()
        dest_dir = trash_root / f"evernote-dedup-{datetime.now():%Y-%m-%d}"
        for dup, _base in pairs:
            body = _strip_frontmatter(dup.read_text(encoding="utf-8")).strip()
            _append_deletion_manifest(vault, run_id, dup, body)
            _move_to_trash(dup, dest_dir)
            deleted += 1

    return {
        "duplicates_found": len(pairs),
        "deleted": deleted,
        "confirmed": confirm,
        "pairs": pairs,
    }


_CLI_DESCRIPTION = """\
Remove exact-duplicate numbered note copies (Title.N.md) left by the Yarle
Evernote export — but ONLY when a copy is byte-for-byte identical to its base
Title.md. The base is always kept; notes that merely share a title (different
content) are left for triage. Dry-run by default; --confirm moves duplicates
to ~/.Trash/evernote-dedup-<date>/ (recoverable) and logs the deletion manifest.
"""

_CLI_EPILOG = """\
Common patterns:

  # Preview which exact-duplicate copies would be removed (no changes)
  %(prog)s --vault ~/Documents/ObsidianVault/Personal

  # Actually remove them (moved to Trash, logged to the deletion manifest)
  %(prog)s --vault ~/Documents/ObsidianVault/Personal --confirm

  # Restrict to one subfolder
  %(prog)s --vault ~/Documents/ObsidianVault/Personal --folder "Evernote/notes/AWS"
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
        "--folder", default=None,
        help="Restrict to one subfolder. Default: whole vault. Skip-list "
             "(wiki/, Personal-backup-*, hidden dirs) still applies.",
    )
    parser.add_argument(
        "--confirm", action="store_true",
        help="Actually remove the duplicate copies. Without this flag the "
             "tool only previews (no files touched).",
    )
    parser.add_argument(
        "--body-only", action="store_true", dest="body_only",
        help="Match on note BODY (frontmatter stripped) rather than byte-exact. "
             "Removes Yarle copies whose classifier frontmatter diverged but "
             "whose content is identical. Base is always kept.",
    )
    args = parser.parse_args()

    summary = dedup_vault(
        vault=args.vault, folder=args.folder, confirm=args.confirm,
        body_only=args.body_only,
    )
    if args.confirm:
        print(
            f"\nduplicates_found={summary['duplicates_found']}, "
            f"deleted={summary['deleted']} "
            f"(moved to ~/.Trash/evernote-dedup-<date>/, logged to manifest)"
        )
    else:
        print(
            f"\nduplicates_found={summary['duplicates_found']} "
            f"(dry-run, no files removed — re-run with --confirm to delete)"
        )
        for dup, base in summary["pairs"][:20]:  # type: ignore[index]
            try:
                rel = dup.relative_to(args.vault)
            except ValueError:
                rel = dup
            print(f"  dup: {rel}")
        extra = int(summary["duplicates_found"]) - 20  # type: ignore[arg-type]
        if extra > 0:
            print(f"  … and {extra} more")


if __name__ == "__main__":
    main()
