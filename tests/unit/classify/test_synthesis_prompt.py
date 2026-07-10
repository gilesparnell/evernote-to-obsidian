"""Tests for the synthesis prompt builder (T4).

RED before scripts/classify/synthesis_prompt.py exists. build_user_prompt is
pure string assembly: it enforces the schema-excerpt and whitelist caps, numbers
source blocks B1..Bn, and carries the citation + word-limit instructions.
"""

from __future__ import annotations

from scripts.classify.synthesis_prompt import (
    PAGE_TEMPLATE,
    SYSTEM_PROMPT,
    build_user_prompt,
)


def _sources(n: int) -> list[dict]:
    return [
        {"title": f"Note {i}", "path": f"Note{i}.md", "text": f"Body text {i}."}
        for i in range(1, n + 1)
    ]


class TestSystemPromptAndTemplate:
    def test_system_prompt_sets_provenance_expectation(self) -> None:
        assert "(src:" in SYSTEM_PROMPT
        # The model must be told never to invent links.
        assert "whitelist" in SYSTEM_PROMPT.lower()

    def test_page_template_carries_both_sentinel_regions(self) -> None:
        for marker in (
            "<!-- @generated:start -->",
            "<!-- @generated:end -->",
            "<!-- @user:start -->",
            "<!-- @user:end -->",
        ):
            assert marker in PAGE_TEMPLATE


class TestBuildUserPrompt:
    def test_numbers_source_blocks_b1_to_bn_with_title_and_path(self) -> None:
        prompt = build_user_prompt(
            topic_slug="julies-finances",
            aliases=["Julie finances"],
            schema_excerpt="CONVENTIONS",
            link_whitelist=["Lisa"],
            sources=_sources(3),
        )

        assert "## Source [B1]: Note 1 (Note1.md)" in prompt
        assert "## Source [B2]: Note 2 (Note2.md)" in prompt
        assert "## Source [B3]: Note 3 (Note3.md)" in prompt
        assert "Body text 2." in prompt

    def test_schema_excerpt_capped_at_1500_chars(self) -> None:
        prompt = build_user_prompt(
            topic_slug="t",
            aliases=[],
            schema_excerpt="X" * 5000,
            link_whitelist=[],
            sources=_sources(1),
        )

        # The 1500-char cap means the full 5000-run never appears verbatim.
        assert "X" * 1501 not in prompt
        assert "X" * 1500 in prompt

    def test_link_whitelist_capped_at_50_titles(self) -> None:
        prompt = build_user_prompt(
            topic_slug="t",
            aliases=[],
            schema_excerpt="",
            link_whitelist=[f"Page {i}" for i in range(80)],
            sources=_sources(1),
        )

        assert "Page 49" in prompt
        assert "Page 50" not in prompt

    def test_topic_slug_and_aliases_present(self) -> None:
        prompt = build_user_prompt(
            topic_slug="julies-finances",
            aliases=["Julie finances", "Kenton financials"],
            schema_excerpt="",
            link_whitelist=[],
            sources=_sources(1),
        )

        assert "julies-finances" in prompt
        assert "Julie finances" in prompt
        assert "Kenton financials" in prompt

    def test_carries_word_limit_and_citation_instruction(self) -> None:
        prompt = build_user_prompt(
            topic_slug="t",
            aliases=[],
            schema_excerpt="",
            link_whitelist=[],
            sources=_sources(1),
        )

        assert "800" in prompt
        assert "(src:" in prompt
