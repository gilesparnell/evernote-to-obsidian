"""Unit 0 (U6): pre-flight sweep of iCloud conflict copies / placeholders.

A topic file that never came from our writer — an iCloud conflict copy
(`slug 2.md`) or a dataless `.slug.md.icloud` placeholder — must be moved out
of `wiki/topics/` before any `load_topics` runs, so it never reaches the
reader. Written RED-first: `scripts/classify/topic_preflight` does not exist yet.
"""

from __future__ import annotations

from pathlib import Path

from scripts.classify.topic_preflight import sweep_topic_conflicts


def _topics_dir(root: Path) -> Path:
    d = root / "wiki" / "topics"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _stub(d: Path, name: str) -> Path:
    path = d / name
    path.write_text(
        "---\ntype: topic\nslug: foo\naliases: [a]\nstatus: active\n---\n",
        encoding="utf-8",
    )
    return path


class TestSweep:
    def test_moves_icloud_numbered_conflict_copy(self, tmp_path: Path) -> None:
        d = _topics_dir(tmp_path)
        good = _stub(d, "foo.md")
        conflict = _stub(d, "foo 2.md")  # iCloud numbered conflict copy

        moved = sweep_topic_conflicts(tmp_path)

        assert conflict in moved
        assert not conflict.exists()
        assert (d / "_quarantine" / "foo 2.md").exists()
        assert good.exists()  # legitimate stub untouched

    def test_moves_conflicted_copy_by_name(self, tmp_path: Path) -> None:
        d = _topics_dir(tmp_path)
        c = d / "bar (conflicted copy).md"
        c.write_text("whatever", encoding="utf-8")

        moved = sweep_topic_conflicts(tmp_path)

        assert c in moved
        assert not c.exists()
        assert (d / "_quarantine" / "bar (conflicted copy).md").exists()

    def test_moves_icloud_dataless_placeholder(self, tmp_path: Path) -> None:
        d = _topics_dir(tmp_path)
        placeholder = d / ".baz.md.icloud"
        placeholder.write_text("", encoding="utf-8")

        moved = sweep_topic_conflicts(tmp_path)

        assert placeholder in moved
        assert not placeholder.exists()
        assert (d / "_quarantine" / ".baz.md.icloud").exists()

    def test_clean_topics_dir_moves_nothing(self, tmp_path: Path) -> None:
        d = _topics_dir(tmp_path)
        _stub(d, "foo.md")
        _stub(d, "foo-bar.md")  # hyphenated slug — legitimate, NOT a conflict

        assert sweep_topic_conflicts(tmp_path) == []
        assert (d / "foo.md").exists()
        assert (d / "foo-bar.md").exists()

    def test_missing_topics_dir_is_a_noop(self, tmp_path: Path) -> None:
        assert sweep_topic_conflicts(tmp_path) == []

    def test_does_not_re_sweep_the_quarantine_dir(self, tmp_path: Path) -> None:
        d = _topics_dir(tmp_path)
        q = d / "_quarantine"
        q.mkdir()
        (q / "foo 2.md").write_text("already quarantined", encoding="utf-8")

        # A prior quarantine must not be touched again or error.
        assert sweep_topic_conflicts(tmp_path) == []
        assert (q / "foo 2.md").exists()
