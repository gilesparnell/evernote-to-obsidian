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


def test_upsert_index_line_inserts_and_replaces_slug_line(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    wiki = vault / "wiki"
    wiki.mkdir(parents=True)
    (wiki / "index.md").write_text(
        "- [[alpha]] — Alpha summary\n"
        "- [[julies-finances]] — Old summary\n",
        encoding="utf-8",
    )

    upsert_index_line(vault, "julies-finances", "New summary")
    upsert_index_line(vault, "zeta", "Zeta summary")

    assert (wiki / "index.md").read_text(encoding="utf-8") == (
        "- [[alpha]] — Alpha summary\n"
        "- [[julies-finances]] — New summary\n"
        "- [[zeta]] — Zeta summary\n"
    )
    assert not list(wiki.glob("*.tmp"))
