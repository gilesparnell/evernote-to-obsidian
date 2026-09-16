from __future__ import annotations

from pathlib import Path

import pytest

from scripts.classify.wiki_io import (
    append_log,
    replace_generated_region,
    upsert_index_line,
)


def test_replace_generated_region_replaces_only_generated_body() -> None:
    original = (
        "intro\n"
        "<!-- @generated:start -->\n"
        "old generated\n"
        "<!-- @generated:end -->\n"
        "\n"
        "<!-- @user:start -->\n"
        "custom user notes\n"
        "<!-- @user:end -->\n"
    )

    result = replace_generated_region(original, "## Summary\nnew generated\n")

    assert "old generated" not in result
    assert "## Summary\nnew generated\n" in result
    assert (
        "<!-- @user:start -->\n"
        "custom user notes\n"
        "<!-- @user:end -->"
    ) in result


def test_replace_generated_region_creates_generated_and_user_regions_when_absent() -> None:
    result = replace_generated_region("# Topic\n", "## Summary\ncreated\n")

    assert result == (
        "# Topic\n"
        "\n"
        "<!-- @generated:start -->\n"
        "## Summary\ncreated\n"
        "<!-- @generated:end -->\n"
        "\n"
        "<!-- @user:start -->\n"
        "<!-- @user:end -->\n"
    )


@pytest.mark.parametrize(
    "text",
    [
        "<!-- @generated:start -->\nbody\n",
        "body\n<!-- @generated:end -->\n",
        "<!-- @generated:start -->\na\n<!-- @generated:start -->\nb\n<!-- @generated:end -->\n",
        "<!-- @generated:start -->\na\n<!-- @generated:end -->\n<!-- @generated:end -->\n",
        "<!-- @generated:end -->\nbody\n<!-- @generated:start -->\n",
        "```markdown\n<!-- @generated:start -->\nbody\n<!-- @generated:end -->\n```\n",
    ],
)
def test_replace_generated_region_rejects_malformed_markers(text: str) -> None:
    with pytest.raises(ValueError):
        replace_generated_region(text, "new\n")


def test_replace_generated_region_preserves_user_region_byte_for_byte() -> None:
    user_region = "<!-- @user:start -->\ncustom *markdown*\n\n- keep me\n<!-- @user:end -->"
    original = (
        "<!-- @generated:start -->\nold\n<!-- @generated:end -->\n"
        "\n"
        f"{user_region}\n"
    )

    result = replace_generated_region(original, "new\n")

    assert user_region in result


def test_append_log_creates_and_appends_atomically_visible_lines(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    append_log(vault, "first entry")
    append_log(vault, "second entry")

    assert (vault / "wiki" / "log.md").read_text(encoding="utf-8") == (
        "first entry\nsecond entry\n"
    )
    assert not list((vault / "wiki").glob("*.tmp"))


def test_upsert_index_line_without_section_replaces_in_place(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    wiki = vault / "wiki"
    wiki.mkdir(parents=True)
    (wiki / "index.md").write_text(
        "- [[alpha]] — Alpha summary\n"
        "- [[julies-finances]] — Old summary\n",
        encoding="utf-8",
    )

    upsert_index_line(vault, "julies-finances", "New summary")

    assert (wiki / "index.md").read_text(encoding="utf-8") == (
        "- [[alpha]] — Alpha summary\n"
        "- [[julies-finances]] — New summary\n"
    )
    assert not list(wiki.glob("*.tmp"))


def test_upsert_index_line_without_section_appends_at_eof(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    wiki = vault / "wiki"
    wiki.mkdir(parents=True)
    (wiki / "index.md").write_text("- [[alpha]] — Alpha summary\n", encoding="utf-8")

    upsert_index_line(vault, "zeta", "Zeta summary")

    assert (wiki / "index.md").read_text(encoding="utf-8") == (
        "- [[alpha]] — Alpha summary\n"
        "- [[zeta]] — Zeta summary\n"
    )
    assert not list(wiki.glob("*.tmp"))


def test_upsert_index_line_appends_absent_slug_inside_existing_section(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    wiki = vault / "wiki"
    wiki.mkdir(parents=True)
    (wiki / "index.md").write_text(
        "# Wiki\n"
        "\n"
        "## Topics\n"
        "- [[alpha]] — Alpha summary\n"
        "\n"
        "## Journal\n"
        "- [[journal-entry]]\n",
        encoding="utf-8",
    )

    upsert_index_line(vault, "julies-finances", "Julie summary", section="## Topics")

    assert (wiki / "index.md").read_text(encoding="utf-8") == (
        "# Wiki\n"
        "\n"
        "## Topics\n"
        "- [[alpha]] — Alpha summary\n"
        "- [[julies-finances]] — Julie summary\n"
        "\n"
        "## Journal\n"
        "- [[journal-entry]]\n"
    )


def test_upsert_index_line_replaces_slug_inside_existing_section_without_duplicate(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    wiki = vault / "wiki"
    wiki.mkdir(parents=True)
    (wiki / "index.md").write_text(
        "# Wiki\n"
        "\n"
        "## Topics\n"
        "- [[alpha]] — Alpha summary\n"
        "- [[julies-finances]] — Old summary\n"
        "\n"
        "## Journal\n",
        encoding="utf-8",
    )

    upsert_index_line(vault, "julies-finances", "New summary", section="## Topics")

    assert (wiki / "index.md").read_text(encoding="utf-8") == (
        "# Wiki\n"
        "\n"
        "## Topics\n"
        "- [[alpha]] — Alpha summary\n"
        "- [[julies-finances]] — New summary\n"
        "\n"
        "## Journal\n"
    )


def test_upsert_index_line_creates_missing_section_at_eof(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    wiki = vault / "wiki"
    wiki.mkdir(parents=True)
    (wiki / "index.md").write_text("# Wiki\n\n## Journal\n- [[today]]\n", encoding="utf-8")

    upsert_index_line(vault, "julies-finances", "Julie summary", section="## Topics")

    assert (wiki / "index.md").read_text(encoding="utf-8") == (
        "# Wiki\n"
        "\n"
        "## Journal\n"
        "- [[today]]\n"
        "\n"
        "## Topics\n"
        "- [[julies-finances]] — Julie summary\n"
    )


def test_upsert_index_line_migrates_same_slug_stray_and_is_idempotent(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    wiki = vault / "wiki"
    wiki.mkdir(parents=True)
    (wiki / "index.md").write_text(
        "# Wiki\n"
        "\n"
        "## Topics\n"
        "- [[alpha]] — Alpha summary\n"
        "\n"
        "## Journal\n"
        "- [[julies-finances]] — Historical stray summary\n"
        "- [[today]]\n",
        encoding="utf-8",
    )

    upsert_index_line(vault, "julies-finances", "New summary", section="## Topics")
    first = (wiki / "index.md").read_text(encoding="utf-8")
    upsert_index_line(vault, "julies-finances", "New summary", section="## Topics")

    assert first == (
        "# Wiki\n"
        "\n"
        "## Topics\n"
        "- [[alpha]] — Alpha summary\n"
        "- [[julies-finances]] — New summary\n"
        "\n"
        "## Journal\n"
        "- [[today]]\n"
    )
    assert (wiki / "index.md").read_text(encoding="utf-8") == first


def test_upsert_index_line_keeps_different_slug_stray_bullet(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    wiki = vault / "wiki"
    wiki.mkdir(parents=True)
    (wiki / "index.md").write_text(
        "# Wiki\n"
        "\n"
        "## Topics\n"
        "\n"
        "## Journal\n"
        "- [[other-topic]] — Leave me alone\n",
        encoding="utf-8",
    )

    upsert_index_line(vault, "julies-finances", "Julie summary", section="## Topics")

    assert (wiki / "index.md").read_text(encoding="utf-8") == (
        "# Wiki\n"
        "\n"
        "## Topics\n"
        "- [[julies-finances]] — Julie summary\n"
        "\n"
        "## Journal\n"
        "- [[other-topic]] — Leave me alone\n"
    )


class TestTransientICloudReadRetry:
    """Vault reads must survive a transient iCloud stall.

    Both vaults are iCloud-synced. macOS FileProvider intermittently fails a
    plain read with `OSError: [Errno 11] Resource deadlock avoided`. Because
    `append_log` runs at the very END of the nightly chain, one such stall
    discarded the entire run's summary and crashed the process after all the
    work was done — which is why `wiki/gardener.md` sat frozen from 10 Aug
    2026 while the chain appeared to be "failing" every night.

    Retry only the transient errno set. A missing file or a permissions
    problem is real and must surface immediately, not after five sleeps.
    """

    def _flaky_reader(self, failures: int, errno_code: int, real_text: str):
        """Return a read_text stand-in that fails `failures` times, then works."""
        state = {"calls": 0}

        def reader(*args, **kwargs):
            state["calls"] += 1
            if state["calls"] <= failures:
                raise OSError(errno_code, "Resource deadlock avoided")
            return real_text

        reader.state = state
        return reader

    def test_append_log_retries_through_a_deadlock_and_succeeds(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        import errno as _errno

        from scripts.classify import wiki_io

        log = tmp_path / "wiki" / "log.md"
        log.parent.mkdir(parents=True)
        log.write_text("first entry\n", encoding="utf-8")

        reader = self._flaky_reader(2, _errno.EDEADLK, "first entry\n")
        monkeypatch.setattr(wiki_io, "_read_once", reader)
        monkeypatch.setattr(wiki_io.time, "sleep", lambda s: None)

        append_log(tmp_path, "second entry")

        assert reader.state["calls"] == 3, "should have retried twice then succeeded"
        assert log.read_text(encoding="utf-8") == "first entry\nsecond entry\n"

    def test_gives_up_after_the_retry_budget(self, tmp_path: Path, monkeypatch) -> None:
        """A persistent failure must still raise — silent data loss is worse."""
        import errno as _errno

        from scripts.classify import wiki_io

        (tmp_path / "wiki").mkdir(parents=True)
        (tmp_path / "wiki" / "log.md").write_text("x\n", encoding="utf-8")

        reader = self._flaky_reader(99, _errno.EDEADLK, "x\n")
        monkeypatch.setattr(wiki_io, "_read_once", reader)
        monkeypatch.setattr(wiki_io.time, "sleep", lambda s: None)

        with pytest.raises(OSError):
            append_log(tmp_path, "entry")
        assert reader.state["calls"] == wiki_io.READ_ATTEMPTS

    def test_does_not_retry_a_real_error(self, tmp_path: Path, monkeypatch) -> None:
        """PermissionError is not transient — surface it on the first try."""
        from scripts.classify import wiki_io

        (tmp_path / "wiki").mkdir(parents=True)
        (tmp_path / "wiki" / "log.md").write_text("x\n", encoding="utf-8")

        state = {"calls": 0}

        def reader(*args, **kwargs):
            state["calls"] += 1
            raise PermissionError(13, "Permission denied")

        monkeypatch.setattr(wiki_io, "_read_once", reader)
        monkeypatch.setattr(wiki_io.time, "sleep", lambda s: None)

        with pytest.raises(PermissionError):
            append_log(tmp_path, "entry")
        assert state["calls"] == 1, "a real error must not burn the retry budget"

    def test_backoff_grows_between_attempts(self, tmp_path: Path, monkeypatch) -> None:
        import errno as _errno

        from scripts.classify import wiki_io

        (tmp_path / "wiki").mkdir(parents=True)
        (tmp_path / "wiki" / "log.md").write_text("x\n", encoding="utf-8")

        delays: list[float] = []
        monkeypatch.setattr(wiki_io, "_read_once", self._flaky_reader(3, _errno.EDEADLK, "x\n"))
        monkeypatch.setattr(wiki_io.time, "sleep", lambda s: delays.append(s))

        append_log(tmp_path, "entry")

        assert len(delays) == 3
        assert delays == sorted(delays), f"backoff must not shrink: {delays}"
        assert delays[-1] > delays[0]

    def test_upsert_index_line_is_protected_too(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """index.md is read by the same nightly step and is equally exposed."""
        import errno as _errno

        from scripts.classify import wiki_io

        idx = tmp_path / "wiki" / "index.md"
        idx.parent.mkdir(parents=True)
        idx.write_text("# Index\n\n## Topics\n", encoding="utf-8")

        reader = self._flaky_reader(1, _errno.EDEADLK, "# Index\n\n## Topics\n")
        monkeypatch.setattr(wiki_io, "_read_once", reader)
        monkeypatch.setattr(wiki_io.time, "sleep", lambda s: None)

        upsert_index_line(tmp_path, "options-trading", "Options trading summary")

        assert reader.state["calls"] == 2
        assert "options-trading" in idx.read_text(encoding="utf-8")
