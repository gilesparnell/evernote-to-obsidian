"""Integration tests for scripts.classify.migrate_vault.

Covers the nine scenarios from plan §Unit 8: routing work/personal context
notes, the unclassified-skip gate, dry-run default, filename conflict
resolution, Evernote dir cleanup, and the migration log.

Uses pytest's tmp_path fixture for real filesystem layouts.
"""

from __future__ import annotations

from pathlib import Path

from scripts.classify.migrate_vault import migrate_vault


_CLASSIFIED_WORK = (
    '---\n'
    'title: "AWS deployment"\n'
    'type: technical\n'
    'org: Amazon\n'
    'context: work\n'
    'up: "[[Technical]]"\n'
    '---\n\n'
    'Body content here.\n'
)
_CLASSIFIED_PERSONAL = (
    '---\n'
    'title: "Recipe"\n'
    'type: recipe\n'
    'org: Personal\n'
    'context: personal\n'
    'up: "[[Personal]]"\n'
    '---\n\n'
    'Body content here.\n'
)
_UNCLASSIFIED = "no frontmatter at all\n"


def _setup_vaults(tmp_path: Path) -> tuple[Path, Path]:
    """Create Personal/ and Business/ vault directories. Return (personal, business)."""
    personal = tmp_path / "Personal"
    business = tmp_path / "Business"
    personal.mkdir()
    business.mkdir()
    return personal, business


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


class TestMigrateVault:
    def test_work_note_in_evernote_moves_to_business_root(self, tmp_path: Path) -> None:
        personal, business = _setup_vaults(tmp_path)
        src = personal / "Evernote" / "notes" / "AWS" / "work-note.md"
        _write(src, _CLASSIFIED_WORK)
        result = migrate_vault(personal=personal, business=business, dry_run=False)
        assert result["to_business"] == 1
        assert (business / "work-note.md").exists()
        assert not src.exists()

    def test_personal_note_in_evernote_moves_to_personal_root(self, tmp_path: Path) -> None:
        personal, business = _setup_vaults(tmp_path)
        src = personal / "Evernote" / "notes" / "Cooking" / "recipe.md"
        _write(src, _CLASSIFIED_PERSONAL)
        result = migrate_vault(personal=personal, business=business, dry_run=False)
        assert result["to_personal_root"] == 1
        assert (personal / "recipe.md").exists()
        assert not src.exists()

    def test_note_outside_evernote_subfolder_is_not_touched(self, tmp_path: Path) -> None:
        personal, business = _setup_vaults(tmp_path)
        existing = personal / "already-flat.md"
        _write(existing, _CLASSIFIED_PERSONAL)
        result = migrate_vault(personal=personal, business=business, dry_run=False)
        assert result["to_business"] == 0
        assert result["to_personal_root"] == 0
        assert existing.exists()  # untouched

    def test_unclassified_note_is_skipped_with_warning(self, tmp_path: Path) -> None:
        personal, business = _setup_vaults(tmp_path)
        src = personal / "Evernote" / "notes" / "AWS" / "unclassified.md"
        _write(src, _UNCLASSIFIED)
        result = migrate_vault(personal=personal, business=business, dry_run=False)
        assert result["skipped_unclassified"] == 1
        assert src.exists()  # NOT moved

    def test_dry_run_by_default_moves_nothing(self, tmp_path: Path) -> None:
        personal, business = _setup_vaults(tmp_path)
        src = personal / "Evernote" / "notes" / "AWS" / "work-note.md"
        _write(src, _CLASSIFIED_WORK)
        result = migrate_vault(personal=personal, business=business)  # no dry_run kw → defaults True
        assert result["dry_run"] is True
        assert result["to_business"] == 1  # counted
        assert src.exists()  # not actually moved
        assert not (business / "work-note.md").exists()

    def test_filename_conflict_gets_suffix(self, tmp_path: Path) -> None:
        personal, business = _setup_vaults(tmp_path)
        # Pre-existing destination
        _write(business / "duplicate.md", "existing\n")
        src = personal / "Evernote" / "notes" / "AWS" / "duplicate.md"
        _write(src, _CLASSIFIED_WORK)
        migrate_vault(personal=personal, business=business, dry_run=False)
        assert (business / "duplicate.md").exists()
        assert (business / "duplicate_2.md").exists()

    def test_evernote_dir_deleted_after_all_notes_migrated(self, tmp_path: Path) -> None:
        personal, business = _setup_vaults(tmp_path)
        src = personal / "Evernote" / "notes" / "AWS" / "only-note.md"
        _write(src, _CLASSIFIED_WORK)
        migrate_vault(personal=personal, business=business, dry_run=False)
        assert not (personal / "Evernote").exists()

    def test_evernote_dir_kept_when_unclassified_notes_remain(
        self, tmp_path: Path
    ) -> None:
        personal, business = _setup_vaults(tmp_path)
        src1 = personal / "Evernote" / "notes" / "AWS" / "classified.md"
        src2 = personal / "Evernote" / "notes" / "AWS" / "unclassified.md"
        _write(src1, _CLASSIFIED_WORK)
        _write(src2, _UNCLASSIFIED)
        migrate_vault(personal=personal, business=business, dry_run=False)
        # The classified one moved; the unclassified one stays — so Evernote/
        # is NOT empty and must NOT be deleted.
        assert (personal / "Evernote").exists()
        assert src2.exists()

    def test_migration_log_written_to_business_root(self, tmp_path: Path) -> None:
        personal, business = _setup_vaults(tmp_path)
        _write(
            personal / "Evernote" / "notes" / "AWS" / "work-note.md",
            _CLASSIFIED_WORK,
        )
        migrate_vault(personal=personal, business=business, dry_run=False)
        log = business / "migration-log.md"
        assert log.exists()
        content = log.read_text(encoding="utf-8")
        assert "work-note.md" in content
