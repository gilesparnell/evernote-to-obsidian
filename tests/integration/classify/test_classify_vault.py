"""Integration tests for scripts.classify.classify_vault.

Uses real .md files via pytest's tmp_path fixture. LM Studio is mocked so
tests don't depend on a running server. The rules classifier runs for
real — it's deterministic and fast.

Covers the eight scenarios from plan §Unit 5 plus two robustness checks
(folder scope, hidden-directory exclusion).
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from scripts.classify.classify_vault import classify_vault, up_for_type


# ---------------------------------------------------------------------------
# Helpers


def _write_note(path: Path, frontmatter: str = "", body: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if frontmatter:
        path.write_text(f"---\n{frontmatter}\n---\n\n{body}\n", encoding="utf-8")
    else:
        path.write_text(body + "\n", encoding="utf-8")


def _lm_result(type_: str, org: str, context: str = "work", confidence: float = 0.95) -> dict:
    return {
        "type": type_,
        "org": org,
        "context": context,
        "people": [],
        "tags": [],
        "confidence": confidence,
        "reason": "mock lm-studio response",
    }


# ---------------------------------------------------------------------------
# Up-map helper


class TestUpForType:
    def test_meeting_routes_to_meetings_moc(self) -> None:
        assert up_for_type("meeting") == "[[Meetings]]"

    def test_interview_routes_to_interview_prep_moc(self) -> None:
        assert up_for_type("interview") == "[[Interview Prep]]"

    def test_unknown_type_falls_back_to_personal_moc(self) -> None:
        assert up_for_type("nonexistent_type_xyz") == "[[Personal]]"


# ---------------------------------------------------------------------------
# Core pipeline behaviour


class TestClassifyVault:
    def test_skips_already_classified_notes(self, tmp_path: Path) -> None:
        note = tmp_path / "already.md"
        _write_note(
            note,
            frontmatter=(
                "title: Already\ntype: meeting\norg: Amazon\n"
                'context: work\nup: "[[Meetings]]"'
            ),
            body="AWS meeting body content",
        )
        result = classify_vault(vault=tmp_path)
        assert result["skipped_already_classified"] == 1
        assert result["auto_classified"] == 0
        assert result["needs_review"] == 0

    def test_high_confidence_rules_writes_frontmatter(self, tmp_path: Path) -> None:
        note = tmp_path / "AWS standup notes.md"
        # Body packed with Amazon-org + meeting-type keywords so rules
        # confidence comfortably exceeds the 0.80 threshold.
        _write_note(
            note,
            body=(
                "AWS S3 EC2 Lambda CloudWatch IAM standup meeting agenda "
                "action items attendees retrospective minutes. Discussing the "
                "deployment pipeline and capacity planning."
            ),
        )
        result = classify_vault(vault=tmp_path)
        assert result["auto_classified"] == 1
        assert result["needs_review"] == 0
        # Verify frontmatter actually written
        from scripts.classify.frontmatter import read_frontmatter
        fm = read_frontmatter(note)
        assert fm["type"] == "meeting"
        assert fm["org"] == "Amazon"
        assert fm["context"] == "work"
        assert fm["up"] == "[[Meetings]]"
        assert "classify_confidence" in fm

    def test_low_rules_then_lm_high_confidence_writes_frontmatter(
        self, tmp_path: Path
    ) -> None:
        note = tmp_path / "ambiguous.md"
        _write_note(
            note,
            body=(
                "Just some random thoughts here about an event that happened "
                "yesterday and a few notes I wanted to capture quickly before "
                "I forget the details about what was discussed."
            ),
        )
        # Rules will return low confidence; mock LM Studio to return high.
        with patch(
            "scripts.classify.classify_vault.lm_classifier.classify",
            return_value=_lm_result("technical", "Amazon", confidence=0.95),
        ):
            result = classify_vault(vault=tmp_path)
        assert result["auto_classified"] == 1
        from scripts.classify.frontmatter import read_frontmatter
        fm = read_frontmatter(note)
        assert fm["type"] == "technical"
        assert fm["org"] == "Amazon"

    def test_both_classifiers_low_confidence_goes_to_review_queue(
        self, tmp_path: Path
    ) -> None:
        note = tmp_path / "ambiguous.md"
        _write_note(
            note,
            body=(
                "Just some random thoughts here about an event that happened "
                "yesterday and a few notes I wanted to capture quickly before "
                "I forget the details about what was discussed."
            ),
        )
        with patch(
            "scripts.classify.classify_vault.lm_classifier.classify",
            return_value=_lm_result("note", "Personal", confidence=0.3),
        ):
            result = classify_vault(vault=tmp_path)
        assert result["auto_classified"] == 0
        assert result["needs_review"] == 1
        # Frontmatter NOT written
        from scripts.classify.frontmatter import read_frontmatter
        assert read_frontmatter(note) == {}
        # Review queue file exists with the note listed
        review = (tmp_path / "classification-review.md").read_text(encoding="utf-8")
        assert "ambiguous" in review

    def test_dry_run_writes_no_files_and_returns_review(self, tmp_path: Path) -> None:
        note = tmp_path / "ambiguous.md"
        _write_note(
            note,
            body=(
                "Just some random thoughts here about an event that happened "
                "yesterday and a few notes I wanted to capture quickly before "
                "I forget the details about what was discussed."
            ),
        )
        with patch(
            "scripts.classify.classify_vault.lm_classifier.classify",
            return_value=_lm_result("note", "Personal", confidence=0.3),
        ):
            result = classify_vault(vault=tmp_path, dry_run=True)
        assert result["needs_review"] == 1
        # No review file on disc in dry-run mode
        assert not (tmp_path / "classification-review.md").exists()
        # No checkpoint either
        assert not (tmp_path / ".classify_checkpoint.json").exists()
        # Source note unchanged
        from scripts.classify.frontmatter import read_frontmatter
        assert read_frontmatter(note) == {}
        # But the review queue text is in the returned payload
        assert "ambiguous" in result["review_queue_md"]

    def test_checkpoint_written_every_interval(self, tmp_path: Path) -> None:
        # Create 7 notes, set checkpoint interval to 3 — checkpoint should
        # appear after notes 3 and 6 (the file is overwritten each time).
        for i in range(7):
            _write_note(tmp_path / f"note-{i:02d}.md", body=f"short body {i}")
        with patch(
            "scripts.classify.classify_vault.lm_classifier.classify",
            return_value=_lm_result("note", "Personal", confidence=0.2),
        ):
            classify_vault(vault=tmp_path, checkpoint_interval=3)
        checkpoint_path = tmp_path / ".classify_checkpoint.json"
        assert checkpoint_path.exists()
        data = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        assert isinstance(data, list)
        assert len(data) >= 6  # at least two checkpoint writes worth of paths

    def test_short_body_goes_to_review_with_too_short_reason(
        self, tmp_path: Path
    ) -> None:
        note = tmp_path / "shorty.md"
        _write_note(note, body="too short")  # well under 50 chars
        result = classify_vault(vault=tmp_path)
        assert result["needs_review"] == 1
        review = (tmp_path / "classification-review.md").read_text(encoding="utf-8")
        assert "too short" in review.lower()

    def test_review_queue_renders_valid_markdown_table(self, tmp_path: Path) -> None:
        _write_note(tmp_path / "short1.md", body="tiny")
        _write_note(tmp_path / "short2.md", body="also tiny")
        classify_vault(vault=tmp_path)
        review = (tmp_path / "classification-review.md").read_text(encoding="utf-8")
        # Header + separator row + two data rows
        assert "| Note | Proposed type | Proposed org | Confidence | Reason |" in review
        assert "|------" in review
        # Two pipe-delimited entries
        data_rows = [l for l in review.splitlines() if l.startswith("| [[")]
        assert len(data_rows) == 2

    def test_folder_scope_limits_processing_to_subfolder(
        self, tmp_path: Path
    ) -> None:
        _write_note(tmp_path / "outside.md", body="outside the folder scope")
        _write_note(
            tmp_path / "Job Hunt" / "inside.md",
            body="application-tracking note inside the Job Hunt folder",
        )
        with patch(
            "scripts.classify.classify_vault.lm_classifier.classify",
            return_value=_lm_result("note", "Personal", confidence=0.2),
        ):
            result = classify_vault(vault=tmp_path, folder="Job Hunt")
        # Only the inside note should have been touched at all.
        assert result["needs_review"] + result["auto_classified"] == 1

    def test_skips_hidden_directories(self, tmp_path: Path) -> None:
        # Files under .obsidian/ must never be touched.
        _write_note(
            tmp_path / ".obsidian" / "config.md",
            body="vault config — must not be classified",
        )
        _write_note(tmp_path / "real.md", body="real note body")
        with patch(
            "scripts.classify.classify_vault.lm_classifier.classify",
            return_value=_lm_result("note", "Personal", confidence=0.2),
        ):
            result = classify_vault(vault=tmp_path)
        # Only the real note should be in scope.
        assert result["needs_review"] + result["auto_classified"] == 1
