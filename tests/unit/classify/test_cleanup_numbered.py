"""Tests for tiered cleanup of remaining Yarle numbered notes."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.classify.cleanup_numbered import (
    classify_numbered,
    delete_near_dups,
    rename_orphans,
)


def _write(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def test_tiering_classifies_orphan_near_dup_review_and_different(
    tmp_path: Path,
) -> None:
    _write(tmp_path / "Orphan.1.md", "orphan body\n")

    _write(tmp_path / "Near.md", "a" * 200)
    _write(tmp_path / "Near.1.md", ("a" * 199) + "b")

    _write(tmp_path / "Review.md", "a" * 100)
    _write(tmp_path / "Review.1.md", ("a" * 95) + ("b" * 5))

    _write(tmp_path / "Different.md", "a" * 100)
    _write(tmp_path / "Different.1.md", "b" * 100)

    tiers = classify_numbered(tmp_path)

    assert tiers["orphan"] == [tmp_path / "Orphan.1.md"]
    assert tiers["near_dup"] == [(tmp_path / "Near.1.md", 0.995)]
    assert tiers["review"] == [(tmp_path / "Review.1.md", 0.95)]
    assert tiers["different"] == [(tmp_path / "Different.1.md", 0.0)]


def test_orphan_rename_dry_run_changes_no_files(tmp_path: Path) -> None:
    _write(tmp_path / "Title.1.md", "numbered orphan\n")
    _write(tmp_path / "Links.md", "[[Title.1]] and [[Title.1|Alias]]\n")

    summary = rename_orphans(tmp_path, confirm=False)

    # dry-run reports the PLAN (1 would-rename) but touches nothing on disc
    assert summary["renamed"] == 1
    assert summary["confirmed"] is False
    assert (tmp_path / "Title.1.md").exists()
    assert not (tmp_path / "Title.md").exists()
    assert (tmp_path / "Links.md").read_text(encoding="utf-8") == (
        "[[Title.1]] and [[Title.1|Alias]]\n"
    )


def test_orphan_rename_confirm_renames_and_rewrites_precise_wikilinks(
    tmp_path: Path,
) -> None:
    _write(tmp_path / "Title.1.md", "numbered orphan\n")
    _write(
        tmp_path / "Links.md",
        (
            "[[Title.1]]\n"
            "[[Title.1|Alias]]\n"
            "[[Title.1#Heading]]\n"
            "[[Title.1#Heading|Alias]]\n"
            "[[Title.1.md]]\n"
            "[[Other]]\n"
            "[[Title.1 Extra]]\n"
        ),
    )

    summary = rename_orphans(tmp_path, confirm=True)

    assert summary["renamed"] == 1
    assert not (tmp_path / "Title.1.md").exists()
    assert (tmp_path / "Title.md").read_text(encoding="utf-8") == (
        "numbered orphan\n"
    )
    assert (tmp_path / "Links.md").read_text(encoding="utf-8") == (
        "[[Title]]\n"
        "[[Title|Alias]]\n"
        "[[Title#Heading]]\n"
        "[[Title#Heading|Alias]]\n"
        "[[Title]]\n"
        "[[Other]]\n"
        "[[Title.1 Extra]]\n"
    )


def test_orphan_rename_ignores_notes_with_existing_base(tmp_path: Path) -> None:
    # A numbered note whose base exists is NOT an orphan — it belongs to the
    # near-dup/different tiers, not the orphan rename. It must be neither renamed
    # nor reported as a collision (that would flood the dry-run with false noise).
    _write(tmp_path / "Title.md", "existing base\n")
    _write(tmp_path / "Title.1.md", "numbered copy\n")

    summary = rename_orphans(tmp_path, confirm=True)

    assert summary["orphans_found"] == 0
    assert summary["renamed"] == 0
    assert summary["skipped_collision"] == []
    assert (tmp_path / "Title.1.md").read_text(encoding="utf-8") == "numbered copy\n"


def test_orphan_rename_multi_orphan_collision_skips_second(tmp_path: Path) -> None:
    # Two orphans map to the same base (no Title.md). The first renames to
    # Title.md; the second would collide with the just-created file → skipped.
    _write(tmp_path / "Title.1.md", "orphan one\n")
    _write(tmp_path / "Title.2.md", "orphan two DIFFERENT\n")

    summary = rename_orphans(tmp_path, confirm=True)

    assert summary["renamed"] == 1
    assert len(summary["skipped_collision"]) == 1
    assert (tmp_path / "Title.md").exists()
    # the loser keeps its numbered name, nothing clobbered
    survivors = {p.name for p in tmp_path.glob("Title*.md")}
    assert "Title.md" in survivors and len(survivors) == 2


def test_dry_run_predicts_multi_orphan_collisions_accurately(tmp_path: Path) -> None:
    # Two orphans → same base. The dry-run must predict renamed=1, collision=1
    # (simulating the sequential claim), NOT report 0 renames / 0 collisions —
    # and must change nothing on disc.
    _write(tmp_path / "Title.1.md", "orphan one\n")
    _write(tmp_path / "Title.2.md", "orphan two DIFFERENT\n")

    summary = rename_orphans(tmp_path, confirm=False)

    assert summary["orphans_found"] == 2
    assert summary["renamed"] == 1
    assert len(summary["skipped_collision"]) == 1
    # nothing actually renamed in dry-run
    assert not (tmp_path / "Title.md").exists()
    assert (tmp_path / "Title.1.md").exists()
    assert (tmp_path / "Title.2.md").exists()


def test_near_dup_delete_confirm_trashes_only_near_dups(tmp_path: Path) -> None:
    _write(tmp_path / "Near.md", "a" * 200)
    _write(tmp_path / "Near.1.md", ("a" * 199) + "b")

    _write(tmp_path / "Review.md", "a" * 100)
    _write(tmp_path / "Review.1.md", ("a" * 95) + ("b" * 5))

    _write(tmp_path / "Different.md", "a" * 100)
    _write(tmp_path / "Different.1.md", "b" * 100)

    trash = tmp_path / "trash"
    summary = delete_near_dups(tmp_path, confirm=True, trash_root=trash)

    assert summary["near_dups_found"] == 1
    assert summary["deleted"] == 1
    assert (tmp_path / "Near.md").exists()
    assert not (tmp_path / "Near.1.md").exists()
    assert list(trash.rglob("Near.1.md"))
    assert (tmp_path / "Review.1.md").exists()
    assert (tmp_path / "Different.1.md").exists()

    manifest = tmp_path / ".classify_deleted_manifest.json"
    data = json.loads(manifest.read_text(encoding="utf-8"))
    assert any("Near.1.md" in entry["path"] for entry in data["deleted"])
