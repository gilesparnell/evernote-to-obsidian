"""Convert Yarle-exported audio markdown links to Obsidian embed wikilinks.

Yarle (the Evernote → Markdown converter that produced this vault) writes
audio attachments as plain markdown links:

    [Evernote 20150930 19-15-54.m4a](./_resources/Audio_from_138_Avon_Road_in_Rye.resources/Evernote 20150930 19-15-54.m4a)

Obsidian renders that as a hyperlink, not an inline audio player. Worse,
the unescaped spaces in the relative path trip Obsidian's link resolver
(it falls back to "open as note", producing "Folder already exists"
toasts and no playback).

This module converts those links to Obsidian embed wikilinks:

    ![[Evernote 20150930 19-15-54.m4a]]

Obsidian's "Shortest path when possible" + "Use [[Wikilinks]]" settings
resolve the basename to the actual file inside `_resources/<note>.resources/`
because audio filenames in this vault are unique (timestamped exports +
ENWatchRecording_* + unknown_filename-<hash>). The `!` prefix tells
Obsidian to render an inline audio player.

Usage:
    scripts/classify/venv/bin/python scripts/classify/audio_link_fix.py \\
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

# Audio markdown-link pattern. Matches:
#   [<text>](<path>)
# where <path> ends in .m4a / .mp3 / .wav (case-insensitive). The leading
# `(?<!!)` is a negative-lookbehind that excludes `![text](path)` — those
# are already embeds and must not be re-wrapped.
_AUDIO_LINK_RE = re.compile(
    r"(?<!!)\[([^\]]+)\]\([^)]+\.(?:m4a|mp3|wav)\)",
    re.IGNORECASE,
)


def convert_audio_links(body: str) -> tuple[str, int]:
    """Replace audio markdown links with Obsidian embed wikilinks.

    Returns ``(new_body, count_converted)``. The wikilink uses the bracket
    text as the embed target — i.e. ``[Evernote 20180510.m4a](./_r/x.m4a)``
    becomes ``![[Evernote 20180510.m4a]]``. Idempotent: existing
    ``![[name]]`` embeds are left alone (the regex's negative lookbehind
    plus the absence of a ``[name](path)`` shape means they never match).
    """
    count = 0

    def _replace(m: re.Match[str]) -> str:
        nonlocal count
        count += 1
        return f"![[{m.group(1)}]]"

    new_body = _AUDIO_LINK_RE.sub(_replace, body)
    return new_body, count


def process_file(path: Path, dry_run: bool) -> int:
    """Read, convert, atomically write a single file. Returns conversion count.

    No write happens when the count is zero — avoids touching mtime and
    triggering iCloud sync churn on files we didn't actually change.
    """
    text = path.read_text(encoding="utf-8")
    new_text, count = convert_audio_links(text)
    if count == 0 or dry_run:
        return count

    # Atomic tmp+rename, mirroring frontmatter.write_frontmatter's pattern
    # for iCloud-safe writes.
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(new_text, encoding="utf-8")
    tmp.replace(path)
    return count


def process_vault(
    vault: Path, folder: str | None, dry_run: bool
) -> dict[str, int]:
    """Walk the vault (or folder), convert every audio link, return a summary.

    Reuses ``classify_vault._iter_md_files`` so the skip-list (wiki/,
    Personal-backup-*/, hidden dirs) is identical to the classifier's.
    """
    files_scanned = 0
    files_changed = 0
    links_converted = 0
    for md_path in _iter_md_files(vault, folder):
        files_scanned += 1
        count = process_file(md_path, dry_run=dry_run)
        if count > 0:
            files_changed += 1
            links_converted += count
    return {
        "files_scanned": files_scanned,
        "files_changed": files_changed,
        "links_converted": links_converted,
    }


_CLI_DESCRIPTION = """\
Convert Yarle-exported `[name.m4a](./_r/...)` markdown links to Obsidian
`![[name.m4a]]` embed wikilinks. Lets Obsidian render an inline audio
player instead of a broken hyperlink. Idempotent + iCloud-safe.
"""

_CLI_EPILOG = """\
Common patterns:

  # Preview what would change (no writes)
  %(prog)s --vault ~/Documents/ObsidianVault/Personal --dry-run

  # Apply across the whole vault
  %(prog)s --vault ~/Documents/ObsidianVault/Personal

  # Restrict to one subfolder (e.g. the AWS notes only)
  %(prog)s --vault ~/Documents/ObsidianVault/Personal \\
    --folder "Evernote/notes/AWS"
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
        help="Restrict to one subfolder. Default: scan the whole vault. "
             "Skip-list (wiki/, Personal-backup-*, hidden dirs) still applies.",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Count what would change; no files written.",
    )
    args = parser.parse_args()

    summary = process_vault(
        vault=args.vault, folder=args.folder, dry_run=args.dry_run,
    )
    mode = "(dry-run)" if args.dry_run else ""
    print(
        f"\nfiles_scanned={summary['files_scanned']}, "
        f"files_changed={summary['files_changed']}, "
        f"links_converted={summary['links_converted']} {mode}"
    )


if __name__ == "__main__":
    main()
