"""Tests for sync_granola — pull new Granola meetings, then classify them.

One action that runs the Granola export (writes new meeting .md files into
Meetings/) and then classifies just that folder. The export hits Granola's
API, so it's injected for tests; the classifier is injected too so we assert
the orchestration without touching the real vault or network.
"""

from __future__ import annotations

from pathlib import Path

from scripts.classify.sync_granola import sync_and_classify


class _ClassifierRecorder:
    def __init__(self, summary=None):
        self.calls = []
        self.summary = summary or {"auto_classified": 3, "needs_review": 0}

    def __call__(self, *, vault, folder, dry_run, log_notes):
        self.calls.append(
            {"vault": vault, "folder": folder, "dry_run": dry_run, "log_notes": log_notes}
        )
        return self.summary


class TestSyncAndClassify:
    def test_pull_then_classify_meetings(self, tmp_path: Path) -> None:
        clf = _ClassifierRecorder()
        result = sync_and_classify(
            tmp_path,
            export_runner=lambda: (0, "exported 3 meetings"),
            classifier=clf,
        )
        assert result["status"] == "ok"
        assert result["classified"] == {"auto_classified": 3, "needs_review": 0}
        # Classifier ran exactly once, scoped to the Meetings folder.
        assert len(clf.calls) == 1
        assert clf.calls[0]["folder"] == "Meetings"

    def test_export_failure_skips_classification(self, tmp_path: Path) -> None:
        clf = _ClassifierRecorder()
        result = sync_and_classify(
            tmp_path,
            export_runner=lambda: (2, "granola api error"),
            classifier=clf,
        )
        assert result["status"] == "export_failed"
        assert result["classified"] is None
        assert clf.calls == []  # never classify if the pull failed

    def test_flags_propagate_to_classifier(self, tmp_path: Path) -> None:
        clf = _ClassifierRecorder()
        sync_and_classify(
            tmp_path,
            folder="Meetings",
            dry_run=True,
            log_notes=True,
            export_runner=lambda: (0, "ok"),
            classifier=clf,
        )
        call = clf.calls[0]
        assert call["dry_run"] is True
        assert call["log_notes"] is True
        assert call["vault"] == tmp_path
