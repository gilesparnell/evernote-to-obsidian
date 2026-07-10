"""Tier and clean up remaining Yarle numbered note copies.

Yarle writes same-title Evernote exports as ``Title.N.md``. After exact
deduplication, remaining numbered notes need safer handling:

* orphan: no ``Title.md`` base exists, so the numbered suffix can be stripped
* near_dup: base exists and body similarity is >= 0.99, so the copy is safe to
  move to Trash
* review: base exists and body similarity is 0.90-0.99, so report only
* different: base exists and body similarity is < 0.90, so leave untouched

Safety: dry-run by default. Use ``--confirm`` for renames or Trash moves.
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

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
from scripts.classify.dedup_notes import _NUMBERED_SUFFIX_RE, _move_to_trash


_WIKILINK_RE = re.compile(r"\[\[([^\]#|]+)(#[^\]|]*)?(\|[^\]]*)?\]\]")


def _base_path_for(path: Path) -> Path | None:
    if not _NUMBERED_SUFFIX_RE.search(path.name):
        return None
    return path.with_name(_NUMBERED_SUFFIX_RE.sub(".md", path.name))


def _body_of(path: Path) -> str:
    return _strip_frontmatter(path.read_text(encoding="utf-8")).strip()


def _similarity(left: Path, right: Path) -> float:
    return SequenceMatcher(None, _body_of(left), _body_of(right)).ratio()


def classify_numbered(vault: Path, folder: str | None = None) -> dict[str, list[Any]]:
    """Classify numbered ``Title.N.md`` notes into cleanup tiers."""
    tiers: dict[str, list[Any]] = {
        "orphan": [],
        "near_dup": [],
        "review": [],
        "different": [],
    }
    for md_path in _iter_md_files(vault, folder):
        base = _base_path_for(md_path)
        if base is None:
            continue
        if not base.exists():
            tiers["orphan"].append(md_path)
            continue

        ratio = round(_similarity(md_path, base), 6)
        if ratio >= 0.99:
            tiers["near_dup"].append((md_path, ratio))
        elif ratio >= 0.90:
            tiers["review"].append((md_path, ratio))
        else:
            tiers["different"].append((md_path, ratio))
    return tiers


def _rewrite_wikilinks(text: str, old_stem: str, new_stem: str) -> tuple[str, int]:
    def replace(match: re.Match[str]) -> str:
        target = match.group(1)
        if target not in {old_stem, f"{old_stem}.md"}:
            return match.group(0)
        rewritten = f"[[{new_stem}{match.group(2) or ''}{match.group(3) or ''}]]"
        replacements.append(rewritten)
        return rewritten

    replacements: list[str] = []
    return _WIKILINK_RE.sub(replace, text), len(replacements)


def _rewrite_links_for_rename(
    vault: Path, old_stem: str, new_stem: str, *, confirm: bool
) -> dict[str, Any]:
    files_changed: list[Path] = []
    links_rewritten = 0

    for md_path in _iter_md_files(vault, folder=None):
        text = md_path.read_text(encoding="utf-8")
        new_text, count = _rewrite_wikilinks(text, old_stem, new_stem)
        if count == 0:
            continue
        files_changed.append(md_path)
        links_rewritten += count
        if confirm:
            tmp = md_path.with_name(md_path.name + ".tmp")
            tmp.write_text(new_text, encoding="utf-8")
            tmp.replace(md_path)

    return {"files_changed": files_changed, "links_rewritten": links_rewritten}


def rename_orphans(vault: Path, confirm: bool = False) -> dict[str, Any]:
    """Rename orphan numbered notes to their base title and rewrite backlinks."""
    # True orphans only: a numbered note whose base does NOT exist. Notes whose
    # base exists belong to the near-dup/different tiers and are out of scope
    # here — including them would flood the dry-run with false "collisions".
    candidates = [
        md_path
        for md_path in _iter_md_files(vault, folder=None)
        if (base := _base_path_for(md_path)) is not None and not base.exists()
    ]
    renamed: list[tuple[Path, Path]] = []
    skipped_collision: list[Path] = []
    link_files_changed: list[Path] = []
    links_rewritten = 0
    # Track base names a rename would claim THIS run, so the dry-run predicts
    # multi-orphan collisions (two orphans → same base) exactly as confirm does,
    # even though no file is created in dry-run mode.
    claimed: set[Path] = set()

    for md_path in candidates:
        target = _base_path_for(md_path)
        if target is None:
            continue
        # Collision if a prior rename this run already claimed the base — checked
        # via the simulated `claimed` set (works in dry-run) AND the filesystem.
        if target in claimed or target.exists():
            skipped_collision.append(md_path)
            continue
        claimed.add(target)

        old_stem = md_path.with_suffix("").name
        new_stem = target.with_suffix("").name
        rewrite_summary = _rewrite_links_for_rename(
            vault, old_stem, new_stem, confirm=confirm
        )
        link_files_changed.extend(rewrite_summary["files_changed"])
        links_rewritten += rewrite_summary["links_rewritten"]
        renamed.append((md_path, target))  # the plan (both modes)
        if confirm:
            md_path.rename(target)

    return {
        "orphans_found": len(candidates),
        "renamed": len(renamed),
        "confirmed": confirm,
        "renames": renamed,
        "skipped_collision": skipped_collision,
        "link_files_changed": link_files_changed,
        "links_rewritten": links_rewritten,
    }


def delete_near_dups(
    vault: Path,
    confirm: bool = False,
    trash_root: Path | None = None,
) -> dict[str, Any]:
    """Move only near-duplicate numbered copies to Trash."""
    trash_root = trash_root or (Path.home() / ".Trash")
    tiers = classify_numbered(vault)
    near_dups = tiers["near_dup"]

    deleted = 0
    if confirm and near_dups:
        run_id = _now_aest_iso()
        dest_dir = trash_root / f"evernote-numbered-cleanup-{datetime.now():%Y-%m-%d}"
        for dup, _ratio in near_dups:
            body = _strip_frontmatter(dup.read_text(encoding="utf-8")).strip()
            _append_deletion_manifest(vault, run_id, dup, body)
            _move_to_trash(dup, dest_dir)
            deleted += 1

    return {
        "near_dups_found": len(near_dups),
        "deleted": deleted,
        "confirmed": confirm,
        "near_dups": near_dups,
        "review": tiers["review"],
        "different": tiers["different"],
    }


def _rel(path: Path, vault: Path) -> Path:
    try:
        return path.relative_to(vault)
    except ValueError:
        return path


def _print_report(vault: Path, tiers: dict[str, list[Any]]) -> None:
    for tier in ("orphan", "near_dup", "review", "different"):
        items = tiers[tier]
        print(f"{tier}={len(items)}")
        for item in items[:20]:
            if isinstance(item, tuple):
                path, ratio = item
                print(f"  {_rel(path, vault)} ({ratio:.4f})")
            else:
                print(f"  {_rel(item, vault)}")
        extra = len(items) - 20
        if extra > 0:
            print(f"  ... and {extra} more")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Tier and safely clean up Yarle numbered notes.",
    )
    parser.add_argument("--vault", required=True, type=Path)
    parser.add_argument("--folder", default=None)
    parser.add_argument("--report", action="store_true")
    parser.add_argument("--rename-orphans", action="store_true")
    parser.add_argument("--delete-near-dups", action="store_true")
    parser.add_argument("--confirm", action="store_true")
    args = parser.parse_args()

    did_action = args.rename_orphans or args.delete_near_dups
    if args.report or not did_action:
        _print_report(args.vault, classify_numbered(args.vault, args.folder))

    if args.rename_orphans:
        summary = rename_orphans(args.vault, confirm=args.confirm)
        mode = "confirmed" if args.confirm else "dry-run"
        print(
            f"rename_orphans {mode}: orphans_found={summary['orphans_found']}, "
            f"renamed={summary['renamed']}, "
            f"links_rewritten={summary['links_rewritten']}, "
            f"skipped_collision={len(summary['skipped_collision'])}"
        )

    if args.delete_near_dups:
        summary = delete_near_dups(args.vault, confirm=args.confirm)
        mode = "confirmed" if args.confirm else "dry-run"
        print(
            f"delete_near_dups {mode}: "
            f"near_dups_found={summary['near_dups_found']}, "
            f"deleted={summary['deleted']}, "
            f"review={len(summary['review'])}, "
            f"different={len(summary['different'])}"
        )


if __name__ == "__main__":
    main()
