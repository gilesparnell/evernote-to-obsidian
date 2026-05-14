"""One-shot fixer for malformed Evernote-export YAML titles.

The .enex → markdown export emits frontmatter where the title value is
written raw, breaking yaml.safe_load when the title contains structural
YAML chars (`:`, leading `-`, leading `*`, etc.). On 2026-05-14 we found
1,540 of 6,375 notes under Personal/Evernote/notes/AWS hit this bug.

This script:
  1. Walks the vault (or a --folder subset), reusing classify_vault's skip-list.
  2. For each note whose frontmatter fails yaml.safe_load:
     a. Locate the `title:` line.
     b. Wrap the value in single quotes (apostrophes doubled per YAML spec).
     c. Re-parse to confirm the fix works.
     d. Write atomically (.tmp + rename) with a 50 ms sleep between files
        to keep iCloud Drive happy on bulk writes.
  3. Reports counts: fixed, already-valid, unfixable, no-frontmatter.

Files where quoting the title doesn't repair the YAML (e.g. multiple
malformed fields) are left untouched and reported as "unfixable" so the
operator can decide what to do — the parser hardening in frontmatter.py
will route them through the classifier as unclassified.
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path

import yaml

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.classify.classify_vault import _iter_md_files  # noqa: E402

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_TITLE_RE = re.compile(r"^title:[ \t]*(.+?)[ \t]*$", re.MULTILINE)
ICLOUD_SLEEP_SECONDS = 0.05


def fix_title_yaml(text: str) -> str | None:
    """Return a fixed copy of `text` with the title quoted, or None.

    Returns None when:
      - the file has no frontmatter
      - the frontmatter already parses (no fix needed)
      - the title line is already quoted (single or double)
      - the title line cannot be found
      - quoting the title still leaves the YAML unparseable
    """
    fm_match = _FRONTMATTER_RE.match(text)
    if not fm_match:
        return None

    yml = fm_match.group(1)

    try:
        yaml.safe_load(yml)
        return None  # already valid
    except yaml.YAMLError:
        pass

    title_match = _TITLE_RE.search(yml)
    if not title_match:
        return None

    raw_value = title_match.group(1)

    # Already quoted? Leave alone — this fixer only handles unquoted titles.
    if (raw_value.startswith("'") and raw_value.endswith("'")) or (
        raw_value.startswith('"') and raw_value.endswith('"')
    ):
        return None

    # YAML single-quote escape: double any internal apostrophes.
    escaped = raw_value.replace("'", "''")
    new_title_line = f"title: '{escaped}'"
    new_yml = yml.replace(title_match.group(0), new_title_line, 1)

    try:
        yaml.safe_load(new_yml)
    except yaml.YAMLError:
        return None  # quoting the title alone didn't repair the YAML

    new_block = f"---\n{new_yml}\n---\n"
    return text.replace(fm_match.group(0), new_block, 1)


def _fix_file(path: Path, dry_run: bool) -> str:
    """Apply the fix to a single file. Returns a status string:
    'fixed' | 'skipped' | 'unfixable'.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return "unfixable"

    # Fast pre-check: if the YAML parses already, skip without rewriting.
    fm_match = _FRONTMATTER_RE.match(text)
    if not fm_match:
        return "skipped"
    try:
        yaml.safe_load(fm_match.group(1))
        return "skipped"  # already valid
    except yaml.YAMLError:
        pass

    fixed = fix_title_yaml(text)
    if fixed is None:
        return "unfixable"
    if fixed == text:
        return "skipped"

    if not dry_run:
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(fixed, encoding="utf-8")
        tmp.replace(path)
        time.sleep(ICLOUD_SLEEP_SECONDS)
    return "fixed"


def fix_vault(
    vault: Path, folder: str | None, dry_run: bool, limit: int | None
) -> dict[str, int]:
    """Walk the vault and apply the title fix. Returns a summary dict."""
    totals = {"scanned": 0, "fixed": 0, "skipped": 0, "unfixable": 0}
    unfixable_paths: list[Path] = []

    for path in _iter_md_files(vault, folder):
        totals["scanned"] += 1
        status = _fix_file(path, dry_run)
        totals[status] += 1
        if status == "unfixable":
            unfixable_paths.append(path)
        if limit is not None and totals["fixed"] >= limit:
            break

    if unfixable_paths:
        print(f"\nUnfixable notes ({len(unfixable_paths)} sample, first 10):")
        for p in unfixable_paths[:10]:
            print(f"  {p}")

    return totals


_CLI_DESCRIPTION = (
    "Quote unquoted titles in Evernote-export YAML frontmatter so "
    "yaml.safe_load can parse them. One-shot data-hygiene tool."
)
_CLI_EPILOG = """
Common patterns:

  # Dry-run on AWS subset (no writes, shows what would happen)
  fix_evernote_titles.py --vault ~/Documents/ObsidianVault/Personal \\
    --folder "Evernote/notes/AWS" --dry-run

  # Apply for real
  fix_evernote_titles.py --vault ~/Documents/ObsidianVault/Personal \\
    --folder "Evernote/notes/AWS"

  # Stop after 5 successful fixes (useful for spot-checking)
  fix_evernote_titles.py --vault ~/Documents/ObsidianVault/Personal \\
    --folder "Evernote/notes/AWS" --limit 5
"""


def main() -> None:
    parser = argparse.ArgumentParser(
        description=_CLI_DESCRIPTION,
        epilog=_CLI_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--vault", required=True, type=Path,
        help="Obsidian vault root.",
    )
    parser.add_argument(
        "--folder", default=None,
        help="Restrict to one subfolder (default: whole vault).",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show what would happen; no writes.",
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Stop after N successful fixes (default: no limit).",
    )
    args = parser.parse_args()

    totals = fix_vault(
        vault=args.vault,
        folder=args.folder,
        dry_run=args.dry_run,
        limit=args.limit,
    )
    mode = "DRY RUN" if args.dry_run else "APPLIED"
    print(
        f"\n{mode}  scanned={totals['scanned']}  "
        f"fixed={totals['fixed']}  "
        f"skipped={totals['skipped']}  "
        f"unfixable={totals['unfixable']}"
    )


if __name__ == "__main__":
    main()
