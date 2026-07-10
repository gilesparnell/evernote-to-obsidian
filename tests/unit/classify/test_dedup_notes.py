"""Tests for dedup_notes — removing exact-duplicate numbered note copies.

Yarle appends `.N` to a note filename when two Evernote notes share a title
(`Title.md`, `Title.1.md`). Some numbered copies are byte-identical to their
base (true duplicates); many are distinct notes that merely share a title.
dedup_notes ONLY removes a numbered copy that is byte-identical to an
existing base `Title.md` — keeping the base, leaving content-differing pairs
for triage. It is dry-run by default; deletions move to a trash dir and are
logged to the shared deletion manifest.
"""

from __future__ import annotations

import json
from pathlib import Path

from scripts.classify.classify_vault import (
    _MANIFEST_FILENAME,
    _append_deletion_manifest,
)
from scripts.classify.dedup_notes import dedup_vault, find_duplicate_copies


class TestDeletionManifestLegacyFormat:
    """A manifest written by an older run is a bare JSON list; the current

    writer expects {"deleted": [...]}. Appending must migrate the legacy list
    in place, preserving old entries, not crash (regression: 2026-07-10 dedup).
    """

    def test_append_to_legacy_list_manifest_migrates_and_preserves(
        self, tmp_path: Path
    ) -> None:
        legacy = [{"path": "old.md", "run_id": "r0", "body_preview": "old"}]
        (tmp_path / _MANIFEST_FILENAME).write_text(json.dumps(legacy), encoding="utf-8")

        _append_deletion_manifest(tmp_path, "r1", tmp_path / "new.md", "new body")

        data = json.loads((tmp_path / _MANIFEST_FILENAME).read_text(encoding="utf-8"))
        assert isinstance(data, dict)
        paths = [e["path"] for e in data["deleted"]]
        assert "old.md" in paths  # legacy entry preserved
        assert "new.md" in paths  # new entry appended


def _write(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


class TestBodyOnlyDedup:
    """--body-only mode: a numbered copy is a duplicate when its BODY matches the

    base after frontmatter is stripped. Yarle copies whose classifier
    frontmatter (people/tags/type) diverged but whose body is identical are the
    target — the byte-exact default misses them.
    """

    def _pair(self, tmp_path: Path) -> None:
        _write(
            tmp_path / "Note.md",
            "---\ntype: personal\npeople: [Julie]\ntags: []\n---\n\nshared body\n",
        )
        _write(
            tmp_path / "Note.1.md",
            "---\ntype: note\npeople: [Jem]\ntags: [polished]\n---\n\nshared body\n",
        )

    def test_frontmatter_diverged_copy_flagged_only_in_body_mode(self, tmp_path: Path) -> None:
        self._pair(tmp_path)
        # byte-exact default: bodies differ by frontmatter → not a duplicate
        assert find_duplicate_copies(tmp_path) == []
        # body-only: same body → flagged, base kept
        pairs = find_duplicate_copies(tmp_path, body_only=True)
        assert pairs == [(tmp_path / "Note.1.md", tmp_path / "Note.md")]

    def test_body_mode_ignores_genuinely_different_bodies(self, tmp_path: Path) -> None:
        _write(tmp_path / "Note.md", "---\ntype: a\n---\n\nbody one\n")
        _write(tmp_path / "Note.1.md", "---\ntype: b\n---\n\nbody two DIFFERENT\n")
        assert find_duplicate_copies(tmp_path, body_only=True) == []

    def test_body_mode_orphan_without_base_not_flagged(self, tmp_path: Path) -> None:
        _write(tmp_path / "Note.1.md", "---\ntype: a\n---\n\norphan body\n")
        assert find_duplicate_copies(tmp_path, body_only=True) == []

    def test_body_mode_confirm_trashes_copy_keeps_base(self, tmp_path: Path) -> None:
        self._pair(tmp_path)
        trash = tmp_path / "trash"
        summary = dedup_vault(tmp_path, confirm=True, trash_root=trash, body_only=True)
        assert summary["deleted"] == 1
        assert not (tmp_path / "Note.1.md").exists()
        assert (tmp_path / "Note.md").exists()


class TestFindDuplicateCopies:
    def test_exact_numbered_copy_is_flagged(self, tmp_path: Path) -> None:
        _write(tmp_path / "Note.md", "identical body\n")
        _write(tmp_path / "Note.1.md", "identical body\n")
        pairs = find_duplicate_copies(tmp_path)
        assert (tmp_path / "Note.1.md", tmp_path / "Note.md") in pairs

    def test_numbered_copy_with_different_content_is_not_flagged(self, tmp_path: Path) -> None:
        _write(tmp_path / "Note.md", "original body\n")
        _write(tmp_path / "Note.1.md", "a genuinely different email\n")
        assert find_duplicate_copies(tmp_path) == []

    def test_numbered_copy_with_no_base_is_not_flagged(self, tmp_path: Path) -> None:
        # The base Note.md does not exist — we can't know which is canonical.
        _write(tmp_path / "Note.1.md", "orphaned numbered note\n")
        assert find_duplicate_copies(tmp_path) == []

    def test_multiple_identical_copies_all_flagged(self, tmp_path: Path) -> None:
        _write(tmp_path / "Note.md", "same\n")
        _write(tmp_path / "Note.1.md", "same\n")
        _write(tmp_path / "Note.2.md", "same\n")
        dups = {d for d, _ in find_duplicate_copies(tmp_path)}
        assert dups == {tmp_path / "Note.1.md", tmp_path / "Note.2.md"}

    def test_base_file_is_never_flagged(self, tmp_path: Path) -> None:
        _write(tmp_path / "Note.md", "same\n")
        _write(tmp_path / "Note.1.md", "same\n")
        dups = {d for d, _ in find_duplicate_copies(tmp_path)}
        assert tmp_path / "Note.md" not in dups

    def test_multi_digit_suffix_handled(self, tmp_path: Path) -> None:
        _write(tmp_path / "Note.md", "same\n")
        _write(tmp_path / "Note.12.md", "same\n")
        dups = {d for d, _ in find_duplicate_copies(tmp_path)}
        assert tmp_path / "Note.12.md" in dups


class TestDedupVault:
    def test_dry_run_deletes_nothing(self, tmp_path: Path) -> None:
        _write(tmp_path / "Note.md", "same\n")
        _write(tmp_path / "Note.1.md", "same\n")
        summary = dedup_vault(tmp_path, confirm=False, trash_root=tmp_path / "trash")
        assert summary["duplicates_found"] == 1
        assert summary["deleted"] == 0
        assert (tmp_path / "Note.1.md").exists()  # untouched in preview

    def test_confirm_removes_copy_keeps_base_and_logs_manifest(self, tmp_path: Path) -> None:
        _write(tmp_path / "Note.md", "same\n")
        _write(tmp_path / "Note.1.md", "same\n")
        trash = tmp_path / "trash"
        summary = dedup_vault(tmp_path, confirm=True, trash_root=trash)

        assert summary["deleted"] == 1
        assert not (tmp_path / "Note.1.md").exists()      # copy removed
        assert (tmp_path / "Note.md").exists()            # base kept
        # Moved to trash (recoverable), not vaporised.
        moved = list(trash.rglob("Note.1.md"))
        assert moved, "duplicate should be moved into the trash dir"
        # Logged to the shared deletion manifest.
        manifest = tmp_path / ".classify_deleted_manifest.json"
        assert manifest.exists()
        data = json.loads(manifest.read_text())
        assert any("Note.1.md" in e["path"] for e in data["deleted"])

    def test_skips_backup_directories(self, tmp_path: Path) -> None:
        # The classifier skip-list (Personal-backup-*) must be respected so we
        # never dedupe inside a backup snapshot.
        _write(tmp_path / "Personal-backup-2026/Note.md", "same\n")
        _write(tmp_path / "Personal-backup-2026/Note.1.md", "same\n")
        summary = dedup_vault(tmp_path, confirm=True, trash_root=tmp_path / "trash")
        assert summary["duplicates_found"] == 0
        assert (tmp_path / "Personal-backup-2026/Note.1.md").exists()
