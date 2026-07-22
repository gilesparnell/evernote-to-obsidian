from __future__ import annotations

from pathlib import Path
from shutil import copytree

import pytest
import yaml

from scripts.classify.topics import Topic, load_topics


FIXTURE_VAULT = Path(__file__).resolve().parents[2] / "fixtures" / "chain"


@pytest.fixture()
def vault(tmp_path: Path) -> Path:
    target = tmp_path / "vault"
    copytree(FIXTURE_VAULT, target)
    return target


@pytest.fixture()
def topics(vault: Path) -> list[Topic]:
    return load_topics(vault)


@pytest.fixture()
def reconcile_backlinks():
    from scripts.classify.topic_backlinks import reconcile_backlinks

    return reconcile_backlinks


def _run(reconcile_backlinks, vault: Path, topics: list[Topic], tmp_path: Path):
    return reconcile_backlinks(
        vault=vault,
        topics=topics,
        json_out=tmp_path / "topic-cache",
        dry_run=False,
    )


def _frontmatter(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    return yaml.safe_load(text.split("---", 2)[1]) or {}


def _body_bytes(path: Path) -> bytes:
    return path.read_bytes().split(b"---", 2)[2]


def _snapshot_tree(root: Path) -> dict[str, tuple[bytes, int]]:
    return {
        path.relative_to(root).as_posix(): (path.read_bytes(), path.stat().st_mtime_ns)
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


class TestTopicBacklinksManagedEntries:
    def test_adds_topics_to_matched_notes_and_appends_to_existing_list(
        self,
        reconcile_backlinks,
        vault: Path,
        topics: list[Topic],
        tmp_path: Path,
    ) -> None:
        _run(reconcile_backlinks, vault, topics, tmp_path)

        assert _frontmatter(vault / "Julie finances title match.md")["topics"] == [
            "[[julie-finances]]"
        ]
        assert _frontmatter(vault / "Body only estate note.md")["topics"] == [
            "[[estate-legal]]"
        ]
        assert _frontmatter(vault / "Hand linked note.md")["topics"] == [
            "[[not-a-registered-topic]]",
            "[[julie-finances]]",
        ]

    def test_hand_written_unregistered_topic_entries_are_preserved_byte_for_byte(
        self,
        reconcile_backlinks,
        vault: Path,
        topics: list[Topic],
        tmp_path: Path,
    ) -> None:
        note = vault / "Hand linked note.md"
        before = note.read_bytes()

        _run(reconcile_backlinks, vault, topics, tmp_path)

        # The hand-written entry's VALUE must survive the rewrite exactly
        # (the topics list itself is re-serialised in the vault's canonical
        # plain style when a managed entry is added alongside it).
        import yaml as _yaml

        assert b"[[not-a-registered-topic]]" in before
        after_text = note.read_text(encoding="utf-8")
        fm = _yaml.safe_load(after_text.split("---")[1])
        assert "[[not-a-registered-topic]]" in fm["topics"]
        # And no forced double-quoting anywhere in the frontmatter.
        assert '"[[' not in after_text

    def test_stale_and_excluded_managed_entries_are_removed(
        self,
        reconcile_backlinks,
        vault: Path,
        topics: list[Topic],
        tmp_path: Path,
    ) -> None:
        _run(reconcile_backlinks, vault, topics, tmp_path)

        assert "topics" not in _frontmatter(vault / "Stale managed entry.md")
        assert "topics" not in _frontmatter(
            vault / "Course" / "Circuit Breakers_ Module 2.md"
        )
        assert "topics" not in _frontmatter(vault / "Excluded by glob.md")

    def test_no_match_note_gets_no_topics_key(
        self,
        reconcile_backlinks,
        vault: Path,
        topics: list[Topic],
        tmp_path: Path,
    ) -> None:
        _run(reconcile_backlinks, vault, topics, tmp_path)

        assert "topics" not in _frontmatter(vault / "Unmatched clean note.md")


class TestTopicBacklinksIdempotence:
    def test_second_run_writes_nothing_when_bytes_and_mtime_are_unchanged(
        self,
        reconcile_backlinks,
        vault: Path,
        topics: list[Topic],
        tmp_path: Path,
    ) -> None:
        _run(reconcile_backlinks, vault, topics, tmp_path)
        before = _snapshot_tree(vault)

        summary = _run(reconcile_backlinks, vault, topics, tmp_path)

        assert _snapshot_tree(vault) == before
        assert summary.updated == 0
        assert summary.removed == 0

    def test_atomic_write_leaves_no_tmp_remnants(
        self,
        reconcile_backlinks,
        vault: Path,
        topics: list[Topic],
        tmp_path: Path,
    ) -> None:
        _run(reconcile_backlinks, vault, topics, tmp_path)

        assert not [
            path.relative_to(vault).as_posix()
            for path in vault.rglob("*")
            if path.name.endswith(".tmp")
        ]


class TestTopicBacklinksOrderingAndPreservation:
    def test_multi_topic_ordering_is_deterministic_and_sorted(
        self,
        reconcile_backlinks,
        vault: Path,
        topics: list[Topic],
        tmp_path: Path,
    ) -> None:
        _run(reconcile_backlinks, vault, topics, tmp_path)

        assert _frontmatter(vault / "Multi topic planning.md")["topics"] == [
            "[[estate-legal]]",
            "[[julie-finances]]",
        ]

    def test_source_note_body_bytes_are_preserved(
        self,
        reconcile_backlinks,
        vault: Path,
        topics: list[Topic],
        tmp_path: Path,
    ) -> None:
        note = vault / "Multi topic planning.md"
        before = _body_bytes(note)

        _run(reconcile_backlinks, vault, topics, tmp_path)

        assert _body_bytes(note) == before


class TestTopicBacklinksFailuresAndSkips:
    def test_malformed_frontmatter_is_skipped_and_reported_without_crashing(
        self,
        reconcile_backlinks,
        vault: Path,
        topics: list[Topic],
        tmp_path: Path,
    ) -> None:
        note = vault / "Malformed frontmatter.md"
        before = note.read_bytes()

        summary = _run(reconcile_backlinks, vault, topics, tmp_path)

        assert note.read_bytes() == before
        assert any("Malformed frontmatter.md" in str(error) for error in summary.errors)

    def test_skip_list_dirs_are_untouched(
        self,
        reconcile_backlinks,
        vault: Path,
        topics: list[Topic],
        tmp_path: Path,
    ) -> None:
        note = vault / "wiki" / "Skipped backlink source.md"
        before = note.read_bytes()

        _run(reconcile_backlinks, vault, topics, tmp_path)

        assert note.read_bytes() == before


class TestFrontmatterStylePreservation:
    def test_untouched_keys_stay_unquoted_and_byte_identical(
        self, tmp_path: Path
    ) -> None:
        import re
        import shutil

        from scripts.classify.topic_backlinks import reconcile_backlinks
        from scripts.classify.topics import load_topics

        fixture = Path(__file__).parents[2] / "fixtures" / "chain"
        vault = tmp_path / "Vault"
        shutil.copytree(fixture, vault)
        note = vault / "Julie finances title match.md"
        before_lines = note.read_text(encoding="utf-8").splitlines()

        reconcile_backlinks(
            vault=vault,
            topics=load_topics(vault),
            json_out=tmp_path / "cache",
        )

        after = note.read_text(encoding="utf-8")
        after_lines = after.splitlines()
        # No frontmatter key may be re-serialised in quoted style.
        fm_end = after_lines[1:].index("---") + 1
        for line in after_lines[1:fm_end]:
            assert not line.startswith('"'), f"quoted key introduced: {line!r}"
        # Every original frontmatter line except topics-related ones survives verbatim.
        topics_re = re.compile(r"^(topics:|- )")
        original_fm = [l for l in before_lines[1 : before_lines[1:].index("---") + 1]
                      if not topics_re.match(l)]
        for line in original_fm:
            assert line in after_lines, f"frontmatter line churned: {line!r}"
        # The backlink itself landed and parses back to the same wikilink.
        assert "topics:" in after
        assert "[[julie-finances]]" in after
