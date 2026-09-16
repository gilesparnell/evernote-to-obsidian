"""Tests for the one-off backfill that re-opens already-exported Granola notes.

The `classified_by: export` stamp only helps notes written after the exporter
change. The notes already on disk carry complete-looking frontmatter with no
provenance, so is_classified() treats them as settled and the classifier never
revisits their hardcoded `context: work`. This backfill stamps them so the
nightly run picks them up.
"""

from __future__ import annotations

from pathlib import Path

from scripts.classify.frontmatter import is_classified, read_frontmatter
from scripts.classify.mark_granola_provisional import mark_granola_provisional


def _note(path: Path, frontmatter: str, body: str = "Some body text.") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\n{frontmatter}\n---\n\n{body}\n", encoding="utf-8")
    return path


_GRANOLA_FM = (
    "date: 2026-09-01\n"
    "granola_id: 3e489f58-dc03-4ad9-a806-d377f86c0a8e\n"
    'up: "[[Meetings]]"\n'
    "type: meeting\n"
    'org: "Personal"\n'
    "context: work"
)


class TestMarkGranolaProvisional:
    def test_stamps_an_unmarked_granola_note(self, tmp_path: Path) -> None:
        note = _note(tmp_path / "Meetings" / "Bed Linen.md", _GRANOLA_FM)
        changed = mark_granola_provisional(tmp_path)
        assert [p.name for p in changed] == ["Bed Linen.md"]
        assert read_frontmatter(note)["classified_by"] == "export"

    def test_stamped_note_becomes_eligible_for_reclassification(
        self, tmp_path: Path
    ) -> None:
        """The point of the whole exercise."""
        note = _note(tmp_path / "Meetings" / "Bed Linen.md", _GRANOLA_FM)
        assert is_classified(note) is True
        mark_granola_provisional(tmp_path)
        assert is_classified(note) is False

    def test_skips_notes_without_a_granola_id(self, tmp_path: Path) -> None:
        """Hand-written notes are not the exporter's output — leave them be."""
        note = _note(
            tmp_path / "hand-written.md",
            'type: meeting\norg: Amazon\ncontext: work\nup: "[[Meetings]]"',
        )
        assert mark_granola_provisional(tmp_path) == []
        assert "classified_by" not in read_frontmatter(note)

    def test_skips_notes_already_claimed_by_the_classifier(
        self, tmp_path: Path
    ) -> None:
        """Re-running must not undo the classifier's work."""
        note = _note(
            tmp_path / "Meetings" / "Done.md",
            _GRANOLA_FM + "\nclassified_by: classifier",
        )
        assert mark_granola_provisional(tmp_path) == []
        assert read_frontmatter(note)["classified_by"] == "classifier"

    def test_is_idempotent(self, tmp_path: Path) -> None:
        _note(tmp_path / "Meetings" / "Bed Linen.md", _GRANOLA_FM)
        first = mark_granola_provisional(tmp_path)
        second = mark_granola_provisional(tmp_path)
        assert len(first) == 1
        assert second == []

    def test_dry_run_reports_without_writing(self, tmp_path: Path) -> None:
        note = _note(tmp_path / "Meetings" / "Bed Linen.md", _GRANOLA_FM)
        changed = mark_granola_provisional(tmp_path, dry_run=True)
        assert [p.name for p in changed] == ["Bed Linen.md"]
        assert "classified_by" not in read_frontmatter(note)

    def test_ignores_the_wiki_directory(self, tmp_path: Path) -> None:
        """wiki/ is operator-curated and uses a different schema."""
        _note(tmp_path / "wiki" / "topics" / "x.md", _GRANOLA_FM)
        assert mark_granola_provisional(tmp_path) == []

    def test_leaves_body_content_untouched(self, tmp_path: Path) -> None:
        note = _note(tmp_path / "Meetings" / "n.md", _GRANOLA_FM, body="Line A\nLine B")
        mark_granola_provisional(tmp_path)
        assert "Line A\nLine B" in note.read_text(encoding="utf-8")

    def test_tolerates_a_note_with_no_frontmatter(self, tmp_path: Path) -> None:
        (tmp_path / "raw.md").write_text("just a body\n", encoding="utf-8")
        assert mark_granola_provisional(tmp_path) == []


class TestICloudWriteThrottle:
    """Bulk vault writes must be throttled — the vaults are iCloud-synced and
    an unpaced burst is what the project convention exists to prevent.
    """

    def test_sleeps_between_writes(self, tmp_path: Path, monkeypatch) -> None:
        import scripts.classify.mark_granola_provisional as mod

        sleeps: list[float] = []
        monkeypatch.setattr(mod.time, "sleep", lambda s: sleeps.append(s))

        for name in ("a", "b", "c"):
            _note(tmp_path / "Meetings" / f"{name}.md", _GRANOLA_FM)
        mark_granola_provisional(tmp_path)

        assert len(sleeps) == 3
        assert all(s == mod.ICLOUD_SLEEP_SECONDS for s in sleeps)

    def test_dry_run_does_not_sleep(self, tmp_path: Path, monkeypatch) -> None:
        import scripts.classify.mark_granola_provisional as mod

        sleeps: list[float] = []
        monkeypatch.setattr(mod.time, "sleep", lambda s: sleeps.append(s))
        _note(tmp_path / "Meetings" / "a.md", _GRANOLA_FM)
        mark_granola_provisional(tmp_path, dry_run=True)
        assert sleeps == []
