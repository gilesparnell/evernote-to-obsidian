import pytest
from pathlib import Path
from scripts.classify_notes import classify_notebook, apply_decisions


def make_note(path: Path, title: str, notebook: str, body: str):
    path.write_text(f"---\ntitle: {title}\nnotebook: {notebook}\n---\n\n{body}")


class TestClassifyNotebook:
    def test_finds_all_notes_in_notebook(self, tmp_path):
        nb = tmp_path / "Work"
        nb.mkdir()
        make_note(nb / "note1.md", "Note 1", "Work", "Content.")
        make_note(nb / "note2.md", "Note 2", "Work", "Content.")
        results = classify_notebook(str(tmp_path), "Work", ollama_model=None)
        assert len(results) == 2

    def test_ignores_notes_in_other_notebooks(self, tmp_path):
        (tmp_path / "Work").mkdir()
        (tmp_path / "Personal").mkdir()
        make_note(tmp_path / "Work" / "work.md", "Work Note", "Work", "Client invoice meeting.")
        make_note(tmp_path / "Personal" / "personal.md", "Personal", "Personal", "Birthday family.")
        results = classify_notebook(str(tmp_path), "Work", ollama_model=None)
        assert len(results) == 1
        assert results[0]["original_notebook"] == "Work"

    def test_returns_empty_list_for_missing_notebook(self, tmp_path):
        results = classify_notebook(str(tmp_path), "NonExistent", ollama_model=None)
        assert results == []

    def test_returns_empty_list_for_empty_notebook(self, tmp_path):
        (tmp_path / "Work").mkdir()
        results = classify_notebook(str(tmp_path), "Work", ollama_model=None)
        assert results == []

    def test_each_result_has_correct_original_notebook(self, tmp_path):
        nb = tmp_path / "Work"
        nb.mkdir()
        make_note(nb / "note.md", "Note", "Work", "Client meeting.")
        results = classify_notebook(str(tmp_path), "Work", ollama_model=None)
        assert results[0]["original_notebook"] == "Work"


class TestApplyDecisions:
    def test_moves_note_to_personal_when_decision_is_personal(self, tmp_path):
        work = tmp_path / "Work"
        personal = tmp_path / "Personal"
        work.mkdir()
        personal.mkdir()
        note = work / "birthday-ideas.md"
        make_note(note, "Birthday Ideas", "Work", "Mum's birthday.")

        stats = apply_decisions(
            [{"path": str(note), "decision": "personal", "title": "Birthday Ideas"}],
            str(tmp_path),
        )
        assert not note.exists()
        assert (personal / "birthday-ideas.md").exists()
        assert stats["moved"] == 1

    def test_moves_note_to_work_when_decision_is_work(self, tmp_path):
        work = tmp_path / "Work"
        personal = tmp_path / "Personal"
        work.mkdir()
        personal.mkdir()
        note = personal / "budget-meeting.md"
        make_note(note, "Budget Meeting", "Personal", "Client invoice.")

        stats = apply_decisions(
            [{"path": str(note), "decision": "work", "title": "Budget Meeting"}],
            str(tmp_path),
        )
        assert not note.exists()
        assert (work / "budget-meeting.md").exists()
        assert stats["moved"] == 1

    def test_skips_pending_decisions(self, tmp_path):
        work = tmp_path / "Work"
        work.mkdir()
        note = work / "undecided.md"
        make_note(note, "Undecided", "Work", "Content.")

        stats = apply_decisions(
            [{"path": str(note), "decision": "pending", "title": "Undecided"}],
            str(tmp_path),
        )
        assert note.exists()
        assert stats["moved"] == 0
        assert stats["skipped"] == 1

    def test_skips_keep_decisions(self, tmp_path):
        work = tmp_path / "Work"
        work.mkdir()
        note = work / "keep-me.md"
        make_note(note, "Keep Me", "Work", "Content.")

        stats = apply_decisions(
            [{"path": str(note), "decision": "keep", "title": "Keep Me"}],
            str(tmp_path),
        )
        assert note.exists()
        assert stats["skipped"] == 1

    def test_skips_when_file_already_in_target_notebook(self, tmp_path):
        work = tmp_path / "Work"
        work.mkdir()
        note = work / "already-correct.md"
        make_note(note, "Already Correct", "Work", "Content.")

        stats = apply_decisions(
            [{"path": str(note), "decision": "work", "title": "Already Correct"}],
            str(tmp_path),
        )
        assert note.exists()
        assert stats["skipped"] == 1
        assert stats["moved"] == 0

    def test_handles_naming_conflict_by_appending_suffix(self, tmp_path):
        work = tmp_path / "Work"
        personal = tmp_path / "Personal"
        work.mkdir()
        personal.mkdir()
        # Pre-existing file with same name in target
        (personal / "same-name.md").write_text("existing note")
        note = work / "same-name.md"
        make_note(note, "Same Name", "Work", "Content.")

        apply_decisions(
            [{"path": str(note), "decision": "personal", "title": "Same Name"}],
            str(tmp_path),
        )
        assert (personal / "same-name.md").exists()  # original preserved
        assert (personal / "same-name_1.md").exists()  # moved with suffix

    def test_creates_target_notebook_dir_if_missing(self, tmp_path):
        work = tmp_path / "Work"
        work.mkdir()
        note = work / "note.md"
        make_note(note, "Note", "Work", "Content.")

        # Personal dir does not exist yet
        stats = apply_decisions(
            [{"path": str(note), "decision": "personal", "title": "Note"}],
            str(tmp_path),
        )
        assert (tmp_path / "Personal" / "note.md").exists()
        assert stats["moved"] == 1

    def test_returns_correct_stats_for_mixed_decisions(self, tmp_path):
        work = tmp_path / "Work"
        personal = tmp_path / "Personal"
        work.mkdir()
        personal.mkdir()

        note_a = work / "birthday.md"
        note_b = work / "meeting.md"
        note_c = work / "unknown.md"
        make_note(note_a, "Birthday", "Work", "Family.")
        make_note(note_b, "Meeting", "Work", "Client.")
        make_note(note_c, "Unknown", "Work", "Content.")

        decisions = [
            {"path": str(note_a), "decision": "personal", "title": "Birthday"},
            {"path": str(note_b), "decision": "keep", "title": "Meeting"},
            {"path": str(note_c), "decision": "pending", "title": "Unknown"},
        ]
        stats = apply_decisions(decisions, str(tmp_path))
        assert stats["moved"] == 1
        assert stats["skipped"] == 2
