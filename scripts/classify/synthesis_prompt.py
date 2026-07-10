"""Synthesis prompt + page template (T4).

The model writes prose only. Everything structural — wikilinks, confidence,
provenance verification, section scaffolding — is derived in code downstream
(see synthesize_topic.py). Keeping the model's job narrow is what makes a 4B
local model (gemma-4-e4b) reliable here.

`SYSTEM_PROMPT` and `PAGE_TEMPLATE` are constants (config, not logic).
`build_user_prompt` assembles the per-run user message and enforces the two
hard caps (schema excerpt, link whitelist) that keep the context budget sane.
"""

from __future__ import annotations

SCHEMA_EXCERPT_CHARS = 1500
LINK_WHITELIST_MAX = 50
WORD_LIMIT = 800

SYSTEM_PROMPT = """\
You compile a personal knowledge-base topic page from source notes. You write \
plain, factual British English prose — nothing else.

Rules you must follow exactly:
- Every sentence you write ends with a source pointer in the form (src: Bn), \
where Bn identifies the numbered source block it came from (B1, B2, ...).
- Use ONLY block numbers that exist in the sources provided. Never cite a block \
that was not given to you.
- Write only what the sources support. Do not guess, embellish, or add outside \
knowledge. If something is your inference rather than stated in a source, do \
not put it in the factual sections at all.
- Only use [[wikilinks]] to page titles on the supplied whitelist. Never invent \
a link. Any link not on the whitelist will be removed.
- If two sources disagree, report both and say so — do not resolve it silently.
- Be concise. This is a reference page, not an essay."""

PAGE_TEMPLATE = """\
<!-- @generated:start -->
## Summary

## Timeline

## Key facts

## Open questions
<!-- @generated:end -->

<!-- @user:start -->
<!-- @user:end -->
"""


def build_user_prompt(
    *,
    topic_slug: str,
    aliases: list[str],
    schema_excerpt: str,
    link_whitelist: list[str],
    sources: list[dict],
) -> str:
    """Assemble the user message for one synthesis run.

    ``sources`` is an ordered list of dicts with ``title``, ``path`` and
    ``text`` keys; the caller has already ranked and budget-trimmed them. They
    are numbered B1..Bn here — that numbering is the provenance contract the
    model cites against and the code later verifies.
    """
    conventions = schema_excerpt[:SCHEMA_EXCERPT_CHARS]
    whitelist = link_whitelist[:LINK_WHITELIST_MAX]

    alias_line = ", ".join(aliases) if aliases else "(none)"
    whitelist_block = (
        "\n".join(f"- {title}" for title in whitelist)
        if whitelist
        else "(no existing pages — do not use any wikilinks)"
    )

    source_blocks = "\n\n".join(
        f"## Source [B{i}]: {src['title']} ({src['path']})\n{src['text']}"
        for i, src in enumerate(sources, start=1)
    )

    return f"""\
VAULT CONVENTIONS
{conventions}

TOPIC
slug: {topic_slug}
aliases: {alias_line}

LINK WHITELIST (only these page titles may be used as [[wikilinks]])
{whitelist_block}

SOURCES
{source_blocks}

TASK
Write the topic page for "{topic_slug}" using only the sources above. Fill these
sections in order: Summary, Timeline, Key facts, Open questions. End every
sentence with its (src: Bn) pointer. Keep the whole page under {WORD_LIMIT} words.
Return the markdown body only — no frontmatter, no code fences."""
