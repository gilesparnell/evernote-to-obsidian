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
