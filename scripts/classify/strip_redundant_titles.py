"""Strip redundant title copies so the filename is the single source of truth.

Title single-source-of-truth migration (plan 2026-05-28-001). Every note
carried its title in up to three places:
  1. Filename                — kept (the one source of truth)
  2. Frontmatter `title:`     — STRIPPED (redundant metadata)
  3. Body `# {title}` H1      — STRIPPED *only when it duplicates the title*

The body-H1 strip is conservative: a leading `# ...` is removed only when
its text matches the note's title (frontmatter title or filename stem minus
the date prefix). Genuine section headings — a note whose first heading is
e.g. "# Property Inspection Feedback" — are left intact.

Safe because nothing downstream reads the frontmatter title (the classifier
derives title from the filename) and no Dataview query references it.

Usage:
    scripts/classify/venv/bin/python scripts/classify/strip_redundant_titles.py \\
        --vault ~/Documents/ObsidianVault/Personal --dry-run
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# Allow direct script invocation in addition to `python -m`.
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.classify.classify_vault import _iter_md_files

_FRONTMATTER_RE = re.compile(r"^(---\s*\n)(.*?)(\n---\s*\n)", re.DOTALL)
_TITLE_LINE_RE = re.compile(r"^title:.*\n?", re.MULTILINE)
# A leading body H1: the first non-empty line after the frontmatter block,
# if it starts with "# ".
_DATE_PREFIX_RE = re.compile(r"^\d{4}-\d{2}-\d{2}\s*-\s*")


def strip_title_frontmatter(text: str) -> tuple[str, bool]:
    """Remove the `title:` line from the frontmatter block only. Returns
    (new_text, changed). A `title:`-looking line in the body is untouched."""
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return text, False
    block = m.group(2)
    new_block, n = _TITLE_LINE_RE.subn("", block)
    if n == 0:
        return text, False
    new_block = new_block.rstrip("\n")
    new_text = m.group(1) + new_block + m.group(3) + text[m.end():]
    return new_text, True


def _title_candidates(filename_stem: str) -> set[str]:
    """The strings a body H1 might match to count as a title duplicate:
    the full filename stem and the stem minus a leading date prefix."""
    candidates = {filename_stem.strip()}
    deprefixed = _DATE_PREFIX_RE.sub("", filename_stem).strip()
    candidates.add(deprefixed)
    return candidates


def strip_matching_body_h1(text: str, filename_stem: str) -> tuple[str, bool]:
    """Remove a leading body `# {title}` heading IFF it duplicates the title.

    'Leading' means the first non-empty line of the body (after the
    frontmatter block). If that line is `# X` and X matches one of the
    title candidates, drop it (and a single trailing blank line). Otherwise
    leave the body untouched — it's a real section heading."""
    m = _FRONTMATTER_RE.match(text)
    body_start = m.end() if m else 0
    head = text[:body_start]
    body = text[body_start:]

    # Find the first non-empty line of the body.
    lines = body.split("\n")
    idx = 0
    while idx < len(lines) and lines[idx].strip() == "":
        idx += 1
    if idx >= len(lines):
        return text, False

    first = lines[idx]
    if not first.startswith("# "):
        return text, False

    heading_text = first[2:].strip()
    if heading_text not in _title_candidates(filename_stem):
        return text, False

    # Drop the heading line and a single immediately-following blank line.
    del lines[idx]
    if idx < len(lines) and lines[idx].strip() == "":
        del lines[idx]
    return head + "\n".join(lines), True


def process_file(path: Path, dry_run: bool) -> dict[str, bool]:
    """Strip title frontmatter + matching body H1 from a single file.
    Returns {title_stripped, h1_stripped}. No write when nothing changed
    (preserves mtime, avoids iCloud churn)."""
    text = path.read_text(encoding="utf-8")
    new_text, title_changed = strip_title_frontmatter(text)
    new_text, h1_changed = strip_matching_body_h1(new_text, path.stem)

    if (title_changed or h1_changed) and not dry_run:
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(new_text, encoding="utf-8")
        tmp.replace(path)

    return {"title_stripped": title_changed, "h1_stripped": h1_changed}


def process_vault(
    vault: Path, folder: str | None, dry_run: bool,
) -> dict[str, int]:
    """Walk the vault (reusing the classifier's skip-list) and strip
    redundant titles. Returns a summary dict."""
    files_scanned = 0
    titles_stripped = 0
    h1s_stripped = 0
    for md_path in _iter_md_files(vault, folder):
        files_scanned += 1
        result = process_file(md_path, dry_run=dry_run)
        if result["title_stripped"]:
            titles_stripped += 1
        if result["h1_stripped"]:
            h1s_stripped += 1
    return {
        "files_scanned": files_scanned,
        "titles_stripped": titles_stripped,
        "h1s_stripped": h1s_stripped,
    }


_CLI_DESCRIPTION = """\
Strip the redundant `title:` frontmatter field (and a leading body H1 that
duplicates the title) so the filename is the single source of truth for a
note's title. Idempotent + iCloud-safe (atomic per-file writes).
"""

_CLI_EPILOG = """\
Common patterns:

  # Preview across the whole vault (no writes)
  %(prog)s --vault ~/Documents/ObsidianVault/Personal --dry-run

  # Apply
  %(prog)s --vault ~/Documents/ObsidianVault/Personal

  # Restrict to one subfolder
  %(prog)s --vault ~/Documents/ObsidianVault/Personal --folder "Meetings"
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
        "--dry-run", action="store_true",
        help="Count what would change; no files written.",
    )
    args = parser.parse_args()

    summary = process_vault(
        vault=args.vault, folder=args.folder, dry_run=args.dry_run,
    )
    mode = " (dry-run)" if args.dry_run else ""
    print(
        f"\nfiles_scanned={summary['files_scanned']}, "
        f"titles_stripped={summary['titles_stripped']}, "
        f"h1s_stripped={summary['h1s_stripped']}{mode}"
    )


if __name__ == "__main__":
    main()
