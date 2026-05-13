import sqlite3
import pytest
from pathlib import Path
from scripts.fix_note_links import process_vault

GUID_A = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
GUID_B = "b2c3d4e5-f6a7-8901-bcde-f12345678901"


@pytest.fixture
def two_notebook_vault(tmp_path):
    """Note A (Notebook A) links to Note B (Notebook B) — cross-notebook link."""
    nb_a = tmp_path / "Notebook A"
    nb_b = tmp_path / "Notebook B"
    nb_a.mkdir()
    nb_b.mkdir()
    (nb_a / "note-a.md").write_text(
        f"---\ntitle: Note A\nnotebook: Notebook A\n---\n\n"
        f"See [Note B](evernote:///view/1/s1/{GUID_B}/{GUID_B}/) for details."
    )
    (nb_b / "note-b.md").write_text(
        "---\ntitle: Note B\nnotebook: Notebook B\n---\n\nContent of Note B."
    )
    return tmp_path


@pytest.fixture
def test_db(tmp_path, two_notebook_vault):
    db_path = tmp_path / "en_backup.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE notes (guid TEXT, title TEXT, notebook_guid TEXT)")
    conn.execute(f"INSERT INTO notes VALUES ('{GUID_A}', 'Note A', 'nb-a')")
    conn.execute(f"INSERT INTO notes VALUES ('{GUID_B}', 'Note B', 'nb-b')")
    conn.commit()
    conn.close()
    return str(db_path)


class TestProcessVault:
    def test_resolves_cross_notebook_link(self, two_notebook_vault, test_db):
        process_vault(str(two_notebook_vault), test_db)
        note_a = (two_notebook_vault / "Notebook A" / "note-a.md").read_text()
        assert "[[note-b]]" in note_a or "[[note-b|" in note_a

    def test_reports_correct_resolved_count(self, two_notebook_vault, test_db):
        stats = process_vault(str(two_notebook_vault), test_db)
        assert stats["total_resolved"] == 1
        assert stats["total_unresolved"] == 0

    def test_reports_correct_file_counts(self, two_notebook_vault, test_db):
        stats = process_vault(str(two_notebook_vault), test_db)
        assert stats["files_processed"] == 2
        assert stats["files_modified"] == 1

    def test_does_not_modify_notes_without_links(self, two_notebook_vault, test_db):
        note_b_before = (two_notebook_vault / "Notebook B" / "note-b.md").read_text()
        process_vault(str(two_notebook_vault), test_db)
        note_b_after = (two_notebook_vault / "Notebook B" / "note-b.md").read_text()
        assert note_b_before == note_b_after

    def test_preserves_evernote_url_when_target_not_imported(self, tmp_path):
        """Link targets not in the vault are kept as evernote:// URLs."""
        vault = tmp_path / "vault"
        vault.mkdir()
        (vault / "note.md").write_text(
            f"---\ntitle: Note\n---\n\n[orphan](evernote:///view/1/s1/{GUID_A}/{GUID_A}/)"
        )
        db_path = tmp_path / "empty.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE notes (guid TEXT, title TEXT, notebook_guid TEXT)")
        conn.commit()
        conn.close()

        process_vault(str(vault), str(db_path))
        content = (vault / "note.md").read_text()
        assert "evernote://" in content

    def test_handles_vault_with_no_evernote_links(self, tmp_path):
        vault = tmp_path / "vault"
        vault.mkdir()
        (vault / "clean.md").write_text(
            "---\ntitle: Clean Note\n---\n\nNo special links here."
        )
        db_path = tmp_path / "empty.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE notes (guid TEXT, title TEXT, notebook_guid TEXT)")
        conn.commit()
        conn.close()

        stats = process_vault(str(vault), str(db_path))
        assert stats["files_modified"] == 0
        assert stats["total_resolved"] == 0
