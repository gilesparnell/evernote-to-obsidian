"""
Post-Yarle link resolver.

Reads en_backup.db (SQLite from evernote-backup) to build a GUID → filename
map, then rewrites unresolved evernote:// links in Obsidian Markdown files to
[[wikilinks]]. Handles cross-notebook links that Yarle cannot resolve on its own.

Usage:
    python scripts/fix_note_links.py \
        --vault /path/to/ObsidianVault/Personal/Evernote \
        --db   ~/evernote-migration/en_backup.db
"""

import argparse
import re
import sqlite3
from pathlib import Path
from typing import Optional

UUID_RE = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
    re.IGNORECASE,
)

EVERNOTE_LINK_RE = re.compile(
    r"\[([^\]]*)\]\(((?:evernote://[^\)]+|https://(?:www|share)\.evernote\.com/[^\)]+))\)",
    re.IGNORECASE,
)

EVERNOTE_WIKILINK_RE = re.compile(
    r"\[\[((?:evernote://[^\]|]+|https://(?:www|share)\.evernote\.com/[^\]|]+))\|([^\]]*)\]\]",
    re.IGNORECASE,
)

FRONTMATTER_TITLE_RE = re.compile(
    r'^---\s*\ntitle:\s*["\']?(.+?)["\']?\s*\n',
    re.MULTILINE,
)


def extract_guid_from_url(url: str) -> Optional[str]:
    """Return the first UUID found in a URL, lowercased, or None."""
    matches = UUID_RE.findall(url)
    return matches[0].lower() if matches else None


def build_title_to_filename_map(vault_dir: str) -> dict[str, str]:
    """
    Scan all .md files under vault_dir and map frontmatter title → filename stem.
    Recurses into subdirectories (one folder per notebook).
    """
    title_map: dict[str, str] = {}
    for md_file in Path(vault_dir).rglob("*.md"):
        content = md_file.read_text(encoding="utf-8")
        match = FRONTMATTER_TITLE_RE.match(content)
        if match:
            title = match.group(1).strip("\"'")
            title_map[title] = md_file.stem
    return title_map


def _normalise_title(t: str) -> str:
    """Lowercase and collapse internal whitespace for fuzzy title matching."""
    return " ".join(t.split()).lower()


def build_guid_map(db_path: str, title_to_filename: dict[str, str]) -> dict[str, str]:
    """
    Query en_backup.db for GUID → title, then resolve titles to Yarle filenames.
    Returns {guid_lowercase: filename_stem} for notes that have a matching .md file.
    Matching falls back through three strategies:
      1. Exact match (fastest, preserves original)
      2. Case-insensitive match (Yarle sometimes changes capitalisation)
      3. Normalised match — case-insensitive + collapsed whitespace (Evernote DB
         sometimes stores double spaces that Yarle strips in the frontmatter)
    """
    lower_title_map = {t.lower(): f for t, f in title_to_filename.items()}
    norm_title_map = {_normalise_title(t): f for t, f in title_to_filename.items()}
    guid_map: dict[str, str] = {}
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.execute("SELECT guid, title FROM notes")
        for guid, title in cursor:
            filename = (
                title_to_filename.get(title)
                or lower_title_map.get(title.lower())
                or norm_title_map.get(_normalise_title(title))
            )
            if filename:
                guid_map[guid.lower()] = filename
    finally:
        conn.close()
    return guid_map


def rewrite_links(content: str, guid_map: dict[str, str]) -> tuple[str, int, int]:
    """
    Replace evernote:// links in both markdown and wikilink formats with Obsidian wikilinks.
    Handles:
      [text](evernote://...)          → [[filename|text]] or [[filename]]
      [[evernote://...|text]]         → [[filename|text]] or [[filename]]
    Returns (new_content, resolved_count, unresolved_count).
    Unresolved links (GUID not in map) are left unchanged.
    """
    resolved = 0
    unresolved = 0

    def _make_wikilink(url: str, display_text: str, original: str) -> str:
        nonlocal resolved, unresolved
        guid = extract_guid_from_url(url)
        if guid and guid in guid_map:
            resolved += 1
            filename = guid_map[guid]
            if display_text and display_text != filename:
                return f"[[{filename}|{display_text}]]"
            return f"[[{filename}]]"
        unresolved += 1
        return original

    def replace_markdown_link(match: re.Match) -> str:
        return _make_wikilink(match.group(2), match.group(1), match.group(0))

    def replace_wikilink(match: re.Match) -> str:
        return _make_wikilink(match.group(1), match.group(2), match.group(0))

    new_content = EVERNOTE_LINK_RE.sub(replace_markdown_link, content)
    new_content = EVERNOTE_WIKILINK_RE.sub(replace_wikilink, new_content)
    return new_content, resolved, unresolved


def process_vault(vault_dir: str, db_path: str) -> dict:
    """
    Orchestrate the full pass: build maps, scan every .md file, rewrite links in place.
    Returns stats: files_processed, files_modified, total_resolved, total_unresolved.
    """
    title_to_filename = build_title_to_filename_map(vault_dir)
    guid_map = build_guid_map(db_path, title_to_filename)
    stats = {
        "files_processed": 0,
        "total_resolved": 0,
        "total_unresolved": 0,
        "files_modified": 0,
    }

    for md_file in Path(vault_dir).rglob("*.md"):
        content = md_file.read_text(encoding="utf-8")
        new_content, resolved, unresolved = rewrite_links(content, guid_map)
        stats["files_processed"] += 1
        stats["total_resolved"] += resolved
        stats["total_unresolved"] += unresolved
        if new_content != content:
            md_file.write_text(new_content, encoding="utf-8")
            stats["files_modified"] += 1

    return stats


def _main():
    parser = argparse.ArgumentParser(description="Rewrite Evernote links to Obsidian wikilinks")
    parser.add_argument("--vault", required=True, help="Path to the Obsidian vault directory")
    parser.add_argument("--db", required=True, help="Path to en_backup.db")
    args = parser.parse_args()

    print(f"Scanning vault: {args.vault}")
    print(f"Using database: {args.db}")
    stats = process_vault(args.vault, args.db)
    print(f"\nDone.")
    print(f"  Files scanned:   {stats['files_processed']}")
    print(f"  Files modified:  {stats['files_modified']}")
    print(f"  Links resolved:  {stats['total_resolved']}")
    print(f"  Links kept as evernote://: {stats['total_unresolved']}")


if __name__ == "__main__":
    _main()
