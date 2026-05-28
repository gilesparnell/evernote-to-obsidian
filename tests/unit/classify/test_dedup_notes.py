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

from scripts.classify.dedup_notes import dedup_vault, find_duplicate_copies


def _write(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


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
