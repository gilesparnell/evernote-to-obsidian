"""Unit tests for scripts.classify.sample_classified."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.classify.sample_classified import (
    parse_filters,
    sample_classified,
)


_FM_TEMPLATE = (
    "---\n"
    "type: {t}\n"
    "org: {o}\n"
    "context: work\n"
    'up: "[[Meetings]]"\n'
    "classify_confidence: 0.9\n"
    "---\n\n"
    "body content for the classified note\n"
)


def _write_classified(path: Path, type_: str = "meeting", org: str = "Amazon") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_FM_TEMPLATE.format(t=type_, o=org), encoding="utf-8")


def _write_unclassified(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("no frontmatter, no classification\n", encoding="utf-8")


class TestSampleClassified:
    def test_returns_n_random_notes_when_enough_available(self, tmp_path: Path) -> None:
        for i in range(20):
            _write_classified(tmp_path / f"note-{i:02d}.md")
        samples = sample_classified(vault=tmp_path, n=5, seed=42)
        assert len(samples) == 5

    def test_returns_all_when_fewer_than_n_available(self, tmp_path: Path) -> None:
        for i in range(3):
            _write_classified(tmp_path / f"note-{i:02d}.md")
        samples = sample_classified(vault=tmp_path, n=10)
        assert len(samples) == 3

    def test_filter_type_returns_only_matching(self, tmp_path: Path) -> None:
        _write_classified(tmp_path / "m1.md", type_="meeting")
        _write_classified(tmp_path / "m2.md", type_="meeting")
        _write_classified(tmp_path / "tech.md", type_="technical")
        samples = sample_classified(
            vault=tmp_path,
            n=10,
            filters=[("type", "meeting")],
        )
        assert len(samples) == 2
        assert all(p.name in {"m1.md", "m2.md"} for p in samples)

    def test_filter_combined_and_logic(self, tmp_path: Path) -> None:
        _write_classified(tmp_path / "aws-meeting.md", type_="meeting", org="Amazon")
        _write_classified(tmp_path / "aws-tech.md", type_="technical", org="Amazon")
        _write_classified(tmp_path / "ts-meeting.md", type_="meeting", org="T-Systems")
        samples = sample_classified(
            vault=tmp_path,
            n=10,
            filters=[("type", "meeting"), ("org", "Amazon")],
        )
        assert len(samples) == 1
        assert samples[0].name == "aws-meeting.md"

    def test_seed_produces_deterministic_sample(self, tmp_path: Path) -> None:
        for i in range(20):
            _write_classified(tmp_path / f"note-{i:02d}.md")
        first = sample_classified(vault=tmp_path, n=5, seed=42)
        second = sample_classified(vault=tmp_path, n=5, seed=42)
        assert [p.name for p in first] == [p.name for p in second]

    def test_unclassified_notes_are_excluded(self, tmp_path: Path) -> None:
        _write_classified(tmp_path / "yes.md")
        _write_unclassified(tmp_path / "no.md")
        samples = sample_classified(vault=tmp_path, n=10)
        assert len(samples) == 1
        assert samples[0].name == "yes.md"

    def test_wiki_directory_is_excluded_by_skip_list(self, tmp_path: Path) -> None:
        # The shared skip-list (Unit 1) must also apply to sampling so we
        # never surface hand-curated wiki content as "classified".
        _write_classified(tmp_path / "wiki" / "concept-x.md")
        _write_classified(tmp_path / "regular.md")
        samples = sample_classified(vault=tmp_path, n=10)
        assert len(samples) == 1
        assert samples[0].name == "regular.md"


class TestParseFilters:
    def test_single_filter_parsed(self) -> None:
        assert parse_filters(["type=meeting"]) == [("type", "meeting")]

    def test_multiple_filters_parsed(self) -> None:
        assert parse_filters(["type=meeting", "org=Amazon"]) == [
            ("type", "meeting"),
            ("org", "Amazon"),
        ]

    def test_invalid_filter_raises_systemexit(self) -> None:
        with pytest.raises(SystemExit):
            parse_filters(["no-equals-sign"])
