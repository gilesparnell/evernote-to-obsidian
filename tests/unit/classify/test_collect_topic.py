"""RED tests for future scripts.classify.collect_topic collector behavior.

T1 deliberately adds these tests before scripts/classify/collect_topic.py
exists. Collection must fail with ModuleNotFoundError until T3 implements it.
"""

from __future__ import annotations

import json
from pathlib import Path
from shutil import copytree

from scripts.classify.classify_vault import (
    _SKIP_TOP_LEVEL_EXACT,
    _SKIP_TOP_LEVEL_PREFIX,
)
from scripts.classify.collect_topic import collect_topic, topic_cache_path
from scripts.classify.topics import Topic


FIXTURE_VAULT = (
    Path(__file__).resolve().parents[2] / "fixtures" / "synthesis"
)


def _topic(slug: str, aliases: list[str]) -> Topic:
    return Topic(
        slug=slug,
        aliases=aliases,
        status="active",
        path=FIXTURE_VAULT / "wiki" / "topics" / f"{slug}.md",
    )


def _collect(vault: Path, topic: Topic, cache_dir: Path) -> dict:
    cache = collect_topic(vault=vault, topic=topic, json_out=cache_dir)
    if isinstance(cache, Path):
        return json.loads(cache.read_text(encoding="utf-8"))
    return cache


class TestCollectTopicMatching:
    def test_matches_title_filename_and_body_case_insensitively(
        self, tmp_path: Path
    ) -> None:
        data = _collect(
            FIXTURE_VAULT,
            _topic("julies-finances", ["Julie finances", "Kenton financials"]),
            tmp_path,
        )

        paths = {source["path"] for source in data["sources"]}

        assert "Julie finances tax notes.md" in paths
        source = next(
            item
            for item in data["sources"]
            if item["path"] == "Julie finances tax notes.md"
        )
        assert source["matched_aliases"] == ["Julie finances", "Kenton financials"]
        assert source["quotes"] == [
            "Julie finances paperwork was reviewed with the Kenton financials summary."
        ]

    def test_body_match_strips_frontmatter(self, tmp_path: Path) -> None:
        vault = tmp_path / "vault"
        vault.mkdir()
        (vault / "Only frontmatter.md").write_text(
            "---\n"
            'title: "Julie finances"\n'
            "---\n\n"
            "This body is unrelated after frontmatter is removed.\n",
            encoding="utf-8",
        )

        data = _collect(vault, _topic("julies-finances", ["Julie finances"]), tmp_path)

        assert data["sources"] == []

    def test_unicode_fold_matches_straight_alias_to_curly_apostrophe_body(
        self, tmp_path: Path
    ) -> None:
        data = _collect(
            FIXTURE_VAULT,
            _topic("julies-finances", ["Julie's money"]),
            tmp_path,
        )

        source = next(
            item for item in data["sources"] if item["path"] == "Untitled.39.md"
        )
        assert source["matched_aliases"] == ["Julie's money"]
        assert source["quotes"] == [
            "The family archive says Julie’s money notes should stay fictional and generic."
        ]

    def test_word_boundary_rejects_substring_near_miss(self, tmp_path: Path) -> None:
        data = _collect(FIXTURE_VAULT, _topic("sean", ["sean"]), tmp_path)

        assert all(source["path"] != "Oceanside plans.md" for source in data["sources"])
        assert data["sources"] == []

    def test_skip_list_and_topic_stubs_are_excluded_as_sources(
        self, tmp_path: Path
    ) -> None:
        assert "wiki" in _SKIP_TOP_LEVEL_EXACT
        assert any(prefix.startswith("Personal-backup") for prefix in _SKIP_TOP_LEVEL_PREFIX)

        data = _collect(
            FIXTURE_VAULT,
            _topic("julies-finances", ["Julie finances"]),
            tmp_path,
        )

        paths = {source["path"] for source in data["sources"]}
        assert "wiki/Skipped Julie finances.md" not in paths
        assert "wiki/topics/julies-finances.md" not in paths
        assert all(not path.startswith("wiki/") for path in paths)

    def test_quotes_are_full_containing_sentences_capped_at_four(
        self, tmp_path: Path
    ) -> None:
        vault = tmp_path / "vault"
        vault.mkdir()
        (vault / "Many matches.md").write_text(
            "Julie finances first sentence. "
            "Julie finances second sentence! "
            "Does Julie finances third sentence work? "
            "Julie finances fourth sentence. "
            "Julie finances fifth sentence should be omitted.\n",
            encoding="utf-8",
        )

        data = _collect(vault, _topic("julies-finances", ["Julie finances"]), tmp_path)

        assert data["sources"][0]["quotes"] == [
            "Julie finances first sentence.",
            "Julie finances second sentence!",
            "Does Julie finances third sentence work?",
            "Julie finances fourth sentence.",
        ]

    def test_unrelated_note_does_not_match(self, tmp_path: Path) -> None:
        data = _collect(
            FIXTURE_VAULT,
            _topic("julies-finances", ["Julie finances", "Julie's money"]),
            tmp_path,
        )

        assert all(source["path"] != "Random garden.md" for source in data["sources"])


class TestCollectTopicCache:
    def test_cache_schema_and_path_follow_data_contract(self, tmp_path: Path) -> None:
        vault = tmp_path / "fixture-vault"
        copytree(FIXTURE_VAULT, vault)
        topic = Topic(
            slug="julies-finances",
            aliases=["Julie finances"],
            status="active",
            path=vault / "wiki" / "topics" / "julies-finances.md",
        )

        data = _collect(vault, topic, tmp_path)
        cache_path = topic_cache_path(vault=vault, slug="julies-finances", json_out=tmp_path)

        assert cache_path == tmp_path / f"{vault.name}-julies-finances.json"
        assert json.loads(cache_path.read_text(encoding="utf-8")) == data
        assert set(data) == {
            "slug",
            "vault",
            "generated_at",
            "source_set_hash",
            "sources",
        }
        assert data["slug"] == "julies-finances"
        assert data["vault"] == str(vault)
        assert data["source_set_hash"].startswith("sha256:")
        assert data["sources"]
        assert set(data["sources"][0]) == {
            "path",
            "title",
            "mtime",
            "matched_aliases",
            "quotes",
        }

    def test_source_set_hash_is_stable_across_runs(self, tmp_path: Path) -> None:
        vault = tmp_path / "fixture-vault"
        copytree(FIXTURE_VAULT, vault)
        topic = Topic(
            slug="julies-finances",
            aliases=["Julie finances"],
            status="active",
            path=vault / "wiki" / "topics" / "julies-finances.md",
        )

        first = _collect(vault, topic, tmp_path)["source_set_hash"]
        second = _collect(vault, topic, tmp_path)["source_set_hash"]

        assert second == first

    def test_source_set_hash_ignores_frontmatter_only_changes(
        self, tmp_path: Path
    ) -> None:
        vault = tmp_path / "fixture-vault"
        copytree(FIXTURE_VAULT, vault)
        note = vault / "Julie finances tax notes.md"
        original = note.read_text(encoding="utf-8")
        topic = Topic(
            slug="julies-finances",
            aliases=["Julie finances"],
            status="active",
            path=vault / "wiki" / "topics" / "julies-finances.md",
        )

        before = _collect(vault, topic, tmp_path)["source_set_hash"]
        note.write_text(
            original.replace('source: fixture', 'source: edited-fixture'),
            encoding="utf-8",
        )
        after = _collect(vault, topic, tmp_path)["source_set_hash"]

        assert after == before

    def test_source_set_hash_changes_when_source_body_changes(
        self, tmp_path: Path
    ) -> None:
        vault = tmp_path / "fixture-vault"
        copytree(FIXTURE_VAULT, vault)
        note = vault / "Julie finances tax notes.md"
        topic = Topic(
            slug="julies-finances",
            aliases=["Julie finances"],
            status="active",
            path=vault / "wiki" / "topics" / "julies-finances.md",
        )

        before = _collect(vault, topic, tmp_path)["source_set_hash"]
        note.write_text(
            note.read_text(encoding="utf-8")
            + "\nJulie finances body changed for hash invalidation.\n",
            encoding="utf-8",
        )
        after = _collect(vault, topic, tmp_path)["source_set_hash"]

        assert after != before

    def test_zero_match_topic_writes_valid_empty_sources_json(
        self, tmp_path: Path
    ) -> None:
        data = _collect(FIXTURE_VAULT, _topic("quiet-topic", ["quiet ledger"]), tmp_path)

        assert data["slug"] == "quiet-topic"
        assert data["source_set_hash"].startswith("sha256:")
        assert data["sources"] == []
        cache_path = topic_cache_path(
            vault=FIXTURE_VAULT,
            slug="quiet-topic",
            json_out=tmp_path,
        )
        assert json.loads(cache_path.read_text(encoding="utf-8"))["sources"] == []

