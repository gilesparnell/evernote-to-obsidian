"""Unit tests for scripts.classify.migrate_legacy_up.

The legacy rewriter turns ``up: "[[Meetings Homepage]]"`` into
``up: "[[Meetings]]"`` across an entire vault. Used once before the new
Meetings MOC goes live to repoint the existing Granola-exported notes.

Atomic writes via .tmp + rename, --dry-run by default, exact count of
rewrites returned. Skips hidden directories (.obsidian, .trash).
"""

from __future__ import annotations

from pathlib import Path

from scripts.classify.migrate_legacy_up import migrate


_LEGACY = """---
title: "X"
up: "[[Meetings Homepage]]"
---

body
"""
_NEW_UP = 'up: "[[Meetings]]"'


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


class TestMigrateLegacyUp:
    def test_rewrites_legacy_pattern_in_simple_note(self, tmp_path: Path) -> None:
        note = tmp_path / "n.md"
        _write(note, _LEGACY)
        result = migrate(tmp_path, dry_run=False)
        assert result["rewrites"] == 1
        assert _NEW_UP in note.read_text(encoding="utf-8")
        assert "Meetings Homepage" not in note.read_text(encoding="utf-8")

    def test_dry_run_does_not_modify_files(self, tmp_path: Path) -> None:
        note = tmp_path / "n.md"
        _write(note, _LEGACY)
        result = migrate(tmp_path, dry_run=True)
        assert result["rewrites"] == 1  # counted, but
        assert "Meetings Homepage" in note.read_text(encoding="utf-8")  # not changed

    def test_counts_rewrites_across_multiple_files(self, tmp_path: Path) -> None:
        for i in range(3):
            _write(tmp_path / f"n{i}.md", _LEGACY)
        _write(tmp_path / "clean.md", "no frontmatter here\n")
        result = migrate(tmp_path, dry_run=False)
        assert result["rewrites"] == 3

    def test_skips_notes_without_legacy_pattern(self, tmp_path: Path) -> None:
        _write(tmp_path / "already.md",
               '---\ntitle: X\nup: "[[Meetings]]"\n---\n\nbody\n')
        _write(tmp_path / "unrelated.md", "no frontmatter\n")
        result = migrate(tmp_path, dry_run=False)
        assert result["rewrites"] == 0

    def test_skips_hidden_directories(self, tmp_path: Path) -> None:
        _write(tmp_path / ".obsidian" / "config.md", _LEGACY)
        _write(tmp_path / "n.md", _LEGACY)
        result = migrate(tmp_path, dry_run=False)
        # Only the top-level note rewritten — .obsidian/ skipped.
        assert result["rewrites"] == 1

    def test_atomic_write_leaves_no_tmp_files(self, tmp_path: Path) -> None:
        _write(tmp_path / "n.md", _LEGACY)
        migrate(tmp_path, dry_run=False)
        leftovers = [p for p in tmp_path.iterdir() if p.name.endswith(".tmp")]
        assert leftovers == []
