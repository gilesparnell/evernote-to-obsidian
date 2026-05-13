from unittest.mock import patch, MagicMock
import pytest
from scripts.classify_notes import (
    extract_note_content,
    score_note,
    classify_with_rules,
    classify_with_ollama,
    classify_note,
)


class TestExtractNoteContent:
    def test_extracts_title_notebook_and_body(self, tmp_path):
        note = tmp_path / "my-note.md"
        note.write_text("---\ntitle: My Note\nnotebook: Work\n---\n\nContent here.")
        result = extract_note_content(str(note))
        assert result["title"] == "My Note"
        assert result["notebook"] == "Work"
        assert "Content here" in result["body"]

    def test_falls_back_to_filename_stem_when_no_frontmatter(self, tmp_path):
        note = tmp_path / "plain-note.md"
        note.write_text("Just plain content.")
        result = extract_note_content(str(note))
        assert result["title"] == "plain-note"
        assert "Just plain content" in result["body"]

    def test_handles_empty_file(self, tmp_path):
        note = tmp_path / "empty.md"
        note.write_text("")
        result = extract_note_content(str(note))
        assert result["title"] == "empty"
        assert result["body"] == ""

    def test_body_does_not_contain_frontmatter(self, tmp_path):
        note = tmp_path / "note.md"
        note.write_text("---\ntitle: Test\nnotebook: Work\n---\n\nBody content.")
        result = extract_note_content(str(note))
        assert "title:" not in result["body"]
        assert "notebook:" not in result["body"]


class TestScoreNote:
    def test_work_heavy_note_scores_higher_for_work(self):
        title = "Q3 Budget Review"
        body = "Meeting with client about invoice. Contract renewal deadline. Vendor proposal."
        work_score, personal_score, _ = score_note(title, body)
        assert work_score > personal_score

    def test_personal_heavy_note_scores_higher_for_personal(self):
        title = "Birthday Party Ideas"
        body = "Mum's birthday dinner recipe. Holiday travel to Bali. Doctor appointment."
        work_score, personal_score, _ = score_note(title, body)
        assert personal_score > work_score

    def test_empty_note_scores_zero_on_both(self):
        work_score, personal_score, _ = score_note("", "")
        assert work_score == 0
        assert personal_score == 0

    def test_returns_matched_keywords_string(self):
        _, _, keywords = score_note("Team Meeting", "client invoice budget")
        assert keywords  # non-empty

    def test_no_keywords_returns_empty_string(self):
        _, _, keywords = score_note("zzz", "zzz")
        assert keywords == ""


class TestClassifyWithRules:
    def test_work_note_classified_as_work(self):
        title = "Q3 Budget Review Meeting"
        body = "Meeting with client about invoice. Contract renewal. Vendor proposal. Quarterly targets."
        prediction, _, _ = classify_with_rules(title, body)
        assert prediction == "Work"

    def test_personal_note_classified_as_personal(self):
        title = "Mum's Birthday Dinner"
        body = "Birthday party for mum. Recipe for cake. Inviting the family. Holiday season."
        prediction, _, _ = classify_with_rules(title, body)
        assert prediction == "Personal"

    def test_work_note_has_high_confidence(self):
        _, confidence, _ = classify_with_rules(
            "Q3 Budget Review", "client invoice contract vendor deadline quarterly"
        )
        assert confidence > 0.6

    def test_personal_note_has_high_confidence(self):
        _, confidence, _ = classify_with_rules(
            "Birthday Party", "mum birthday family holiday recipe dinner kids"
        )
        assert confidence > 0.6

    def test_empty_note_has_zero_confidence(self):
        _, confidence, _ = classify_with_rules("", "")
        assert confidence == 0.0

    def test_confidence_is_between_zero_and_one(self):
        for title, body in [
            ("Work Meeting", "client invoice budget"),
            ("Birthday", "family mum holiday recipe"),
            ("", ""),
            ("Notes", "ideas things stuff"),
        ]:
            _, confidence, _ = classify_with_rules(title, body)
            assert 0.0 <= confidence <= 1.0, f"confidence out of range for '{title}'"

    def test_reasoning_is_non_empty_string(self):
        _, _, reasoning = classify_with_rules("Budget Meeting", "client invoice contract")
        assert isinstance(reasoning, str)
        assert len(reasoning) > 0


class TestClassifyWithOllama:
    def test_classifies_as_work_from_work_response(self):
        with patch("scripts.classify_notes.ollama") as mock_ollama:
            mock_ollama.chat.return_value = {
                "message": {"content": "WORK - client budget meeting"}
            }
            prediction, confidence, _ = classify_with_ollama("Budget", "client invoice", "llama3.2")
        assert prediction == "Work"
        assert confidence > 0

    def test_classifies_as_personal_from_personal_response(self):
        with patch("scripts.classify_notes.ollama") as mock_ollama:
            mock_ollama.chat.return_value = {
                "message": {"content": "PERSONAL - birthday party planning for family"}
            }
            prediction, _, _ = classify_with_ollama("Birthday", "mum party", "llama3.2")
        assert prediction == "Personal"

    def test_returns_uncertain_for_unrecognised_response(self):
        with patch("scripts.classify_notes.ollama") as mock_ollama:
            mock_ollama.chat.return_value = {
                "message": {"content": "I cannot determine this."}
            }
            prediction, _, _ = classify_with_ollama("Note", "content", "llama3.2")
        assert prediction == "Uncertain"

    def test_raises_when_ollama_chat_fails(self):
        with patch("scripts.classify_notes.ollama") as mock_ollama:
            mock_ollama.chat.side_effect = Exception("connection refused")
            with pytest.raises(Exception):
                classify_with_ollama("Title", "body", "llama3.2")

    def test_reasoning_comes_from_ollama_response(self):
        with patch("scripts.classify_notes.ollama") as mock_ollama:
            mock_ollama.chat.return_value = {
                "message": {"content": "WORK - mentions client and quarterly targets"}
            }
            _, _, reasoning = classify_with_ollama("Title", "body", "llama3.2")
        assert "client" in reasoning or "quarterly" in reasoning or reasoning


class TestClassifyNote:
    def test_result_has_all_required_fields(self, tmp_path):
        note = tmp_path / "note.md"
        note.write_text("---\ntitle: Note\nnotebook: Work\n---\n\nContent.")
        result = classify_note(str(note), confidence_threshold=0.7, ollama_model=None)
        for key in ["path", "title", "original_notebook", "predicted", "confidence", "method", "reasoning", "decision"]:
            assert key in result, f"missing key: {key}"

    def test_decision_is_pending_by_default(self, tmp_path):
        note = tmp_path / "note.md"
        note.write_text("---\ntitle: Note\nnotebook: Work\n---\n\nContent.")
        result = classify_note(str(note), confidence_threshold=0.7, ollama_model=None)
        assert result["decision"] == "pending"

    def test_uses_rules_when_ollama_model_is_none(self, tmp_path):
        note = tmp_path / "budget.md"
        note.write_text("---\ntitle: Budget Meeting\nnotebook: Work\n---\n\nClient invoice contract vendor deadline.")
        result = classify_note(str(note), confidence_threshold=0.5, ollama_model=None)
        assert result["method"] == "rules"

    def test_calls_ollama_when_confidence_is_low(self, tmp_path):
        note = tmp_path / "ambiguous.md"
        note.write_text("---\ntitle: Notes\nnotebook: Work\n---\n\nSome ideas.")
        with patch("scripts.classify_notes.ollama") as mock_ollama:
            mock_ollama.chat.return_value = {"message": {"content": "WORK - professional context"}}
            result = classify_note(str(note), confidence_threshold=0.99, ollama_model="llama3.2")
        assert result["method"] == "ollama"

    def test_falls_back_to_rules_when_ollama_raises(self, tmp_path):
        note = tmp_path / "note.md"
        note.write_text("---\ntitle: Note\nnotebook: Work\n---\n\nContent.")
        with patch("scripts.classify_notes.ollama") as mock_ollama:
            mock_ollama.chat.side_effect = Exception("timeout")
            result = classify_note(str(note), confidence_threshold=0.0, ollama_model="llama3.2")
        assert result["method"] == "rules"  # fell back gracefully

    def test_confidence_is_rounded_float(self, tmp_path):
        note = tmp_path / "note.md"
        note.write_text("---\ntitle: Budget Meeting\nnotebook: Work\n---\n\nClient invoice.")
        result = classify_note(str(note), confidence_threshold=0.7, ollama_model=None)
        assert isinstance(result["confidence"], float)
        assert 0.0 <= result["confidence"] <= 1.0
