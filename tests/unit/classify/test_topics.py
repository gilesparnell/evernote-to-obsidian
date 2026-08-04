"""RED tests for future scripts.classify.topics topic-stub discovery.

T1 deliberately adds these tests before scripts/classify/topics.py exists.
Collection must fail with ModuleNotFoundError until T2 implements the module.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.classify.topics import (
    QuarantinedTopic,
    Topic,
    load_topic_report,
    load_topics,
    slugify,
    validate,
)


FIXTURE_VAULT = (
    Path(__file__).resolve().parents[2] / "fixtures" / "synthesis"
)


def _write_topic_stub(
    root: Path,
    filename: str,
    *,
    slug: str | None = None,
    aliases: str = "[Example alias]",
    status: str = "active",
    type_: str = "topic",
) -> Path:
    topics_dir = root / "wiki" / "topics"
    topics_dir.mkdir(parents=True, exist_ok=True)
    path = topics_dir / filename
    path.write_text(
        "---\n"
        f"type: {type_}\n"
        f"slug: {slug or path.stem}\n"
        f"aliases: {aliases}\n"
        f"status: {status}\n"
        "---\n\n"
        f"# {path.stem}\n",
        encoding="utf-8",
    )
    return path


class TestLoadTopics:
    def test_parses_active_topic_stub_frontmatter(self) -> None:
        topics = load_topics(FIXTURE_VAULT)
        julies = next(topic for topic in topics if topic.slug == "julies-finances")

        assert julies.path == FIXTURE_VAULT / "wiki" / "topics" / "julies-finances.md"
        assert julies.slug == "julies-finances"
        assert julies.aliases == [
            "Julie finances",
            "Julie's money",
            "Kenton financials",
            "mom money",
        ]
        assert julies.status == "active"

    def test_slug_mismatch_is_quarantined_not_raised(self, tmp_path: Path) -> None:
        bad = _write_topic_stub(tmp_path, "julies-finances.md", slug="wrong-slug")

        report = load_topic_report(tmp_path)

        assert report.topics == []
        assert [q.path for q in report.quarantined] == [bad]
        assert "wrong-slug" in report.quarantined[0].reason
        # load_topics never raises on a bad file — the safety net
        assert load_topics(tmp_path) == []

    def test_paused_stubs_are_skipped(self, tmp_path: Path) -> None:
        _write_topic_stub(tmp_path, "active-topic.md", aliases="[Active alias]")
        _write_topic_stub(
            tmp_path,
            "paused-topic.md",
            aliases="[Paused alias]",
            status="paused",
        )

        topics = load_topics(tmp_path)

        assert [topic.slug for topic in topics] == ["active-topic"]

    def test_invalid_yaml_reports_file_and_keeps_other_topics_loadable(
        self, tmp_path: Path
    ) -> None:
        good = _write_topic_stub(tmp_path, "good-topic.md", aliases="[Good alias]")
        bad = tmp_path / "wiki" / "topics" / "broken-topic.md"
        bad.write_text(
            "---\n"
            "type: topic\n"
            "slug: broken-topic\n"
            "aliases: [Broken alias\n"
            "status: active\n"
            "---\n",
            encoding="utf-8",
        )

        report = load_topic_report(tmp_path)

        assert [t.slug for t in report.topics] == ["good-topic"]
        assert [q.path for q in report.quarantined] == [bad]
        reason = report.quarantined[0].reason
        assert "YAML" in reason or "yaml" in reason

    def test_bare_string_aliases_is_quarantined_not_raised(self, tmp_path: Path) -> None:
        bad = _write_topic_stub(
            tmp_path,
            "string-alias.md",
            aliases="single bare alias",
        )

        report = load_topic_report(tmp_path)

        assert report.topics == []
        assert [q.path for q in report.quarantined] == [bad]
        assert "aliases" in report.quarantined[0].reason

    def test_empty_alias_list_loads_without_crashing(self, tmp_path: Path) -> None:
        _write_topic_stub(tmp_path, "empty-aliases.md", aliases="[]")

        topics = load_topics(tmp_path)

        assert len(topics) == 1
        assert topics[0].slug == "empty-aliases"
        assert topics[0].aliases == []

    def test_missing_topic_type_is_ignored_without_error(self, tmp_path: Path) -> None:
        _write_topic_stub(
            tmp_path,
            "not-a-topic.md",
            aliases="[Not a topic]",
            type_="note",
        )
        _write_topic_stub(tmp_path, "real-topic.md", aliases="[Real topic]")

        topics = load_topics(tmp_path)

        assert [topic.slug for topic in topics] == ["real-topic"]


class TestExcludeField:
    def test_exclude_parsed_from_frontmatter(self, tmp_path: Path) -> None:
        path = tmp_path / "wiki" / "topics" / "t.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "---\ntype: topic\nslug: t\naliases: [a]\n"
            "exclude: ['Circuit Breakers_*', 'Evernote/*']\nstatus: active\n---\n",
            encoding="utf-8",
        )
        topics = load_topics(tmp_path)
        assert topics[0].exclude == ["Circuit Breakers_*", "Evernote/*"]

    def test_exclude_defaults_to_empty_when_absent(self, tmp_path: Path) -> None:
        path = tmp_path / "wiki" / "topics" / "t.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "---\ntype: topic\nslug: t\naliases: [a]\nstatus: active\n---\n",
            encoding="utf-8",
        )
        assert load_topics(tmp_path)[0].exclude == []

    def test_exclude_as_bare_string_is_quarantined_not_raised(self, tmp_path: Path) -> None:
        path = tmp_path / "wiki" / "topics" / "t.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "---\ntype: topic\nslug: t\naliases: [a]\nexclude: nope\nstatus: active\n---\n",
            encoding="utf-8",
        )
        report = load_topic_report(tmp_path)
        assert report.topics == []
        assert [q.path for q in report.quarantined] == [path]
        assert "exclude" in report.quarantined[0].reason


class TestSlugify:
    def test_nfkd_slugifies_curly_or_straight_apostrophe(self) -> None:
        assert slugify("Julie's") == "julies"
        assert slugify("Julie’s") == "julies"

    def test_slugifies_to_canonical_lower_hyphen_form(self) -> None:
        assert slugify("  Kenton Financials / Mom Money  ") == (
            "kenton-financials-mom-money"
        )


class TestValidateTopics:
    def test_alias_overlap_across_two_stubs_is_an_error(self, tmp_path: Path) -> None:
        topic_a = Topic(
            slug="julies-finances",
            aliases=["Julie finances", "Shared alias"],
            status="active",
            path=tmp_path / "wiki" / "topics" / "julies-finances.md",
        )
        topic_b = Topic(
            slug="kenton-finances",
            aliases=["shared alias", "Kenton financials"],
            status="active",
            path=tmp_path / "wiki" / "topics" / "kenton-finances.md",
        )

        with pytest.raises(ValueError, match="Shared alias|shared alias"):
            validate([topic_a, topic_b])

    def test_slug_collision_is_an_error(self, tmp_path: Path) -> None:
        topic_a = Topic(
            slug="julies-finances",
            aliases=["Julie finances"],
            status="active",
            path=tmp_path / "wiki" / "topics" / "julies-finances.md",
        )
        topic_b = Topic(
            slug="julies-finances",
            aliases=["Kenton financials"],
            status="active",
            path=tmp_path / "wiki" / "topics" / "duplicate.md",
        )

        with pytest.raises(ValueError, match="julies-finances"):
            validate([topic_a, topic_b])


class TestFailSoftLoad:
    """The safety net: one bad topic file must never brick the vault's chain."""

    def test_alias_collision_quarantines_later_keeps_earlier(self, tmp_path: Path) -> None:
        # sorted glob order: alpha.md before beta.md → alpha wins, beta quarantined.
        _write_topic_stub(tmp_path, "alpha.md", aliases="[Shared alias]")
        beta = _write_topic_stub(tmp_path, "beta.md", aliases="[shared alias]")

        report = load_topic_report(tmp_path)

        assert [t.slug for t in report.topics] == ["alpha"]
        assert [q.path for q in report.quarantined] == [beta]
        assert "alias" in report.quarantined[0].reason.lower()

    def test_one_bad_file_never_blocks_the_rest(self, tmp_path: Path) -> None:
        _write_topic_stub(tmp_path, "good-one.md", aliases="[Alpha]")
        _write_topic_stub(tmp_path, "good-two.md", aliases="[Beta]")
        _write_topic_stub(tmp_path, "bad.md", slug="mismatch", aliases="[Gamma]")

        topics = load_topics(tmp_path)

        assert sorted(t.slug for t in topics) == ["good-one", "good-two"]

    def test_report_is_empty_for_a_clean_vault(self, tmp_path: Path) -> None:
        _write_topic_stub(tmp_path, "clean.md", aliases="[Clean]")

        report = load_topic_report(tmp_path)

        assert [t.slug for t in report.topics] == ["clean"]
        assert report.quarantined == []
        assert isinstance(report.quarantined, list)

    def test_quarantined_topic_record_shape(self, tmp_path: Path) -> None:
        bad = _write_topic_stub(tmp_path, "x.md", slug="not-x")

        record = load_topic_report(tmp_path).quarantined[0]

        assert isinstance(record, QuarantinedTopic)
        assert record.path == bad
        assert isinstance(record.reason, str) and record.reason

