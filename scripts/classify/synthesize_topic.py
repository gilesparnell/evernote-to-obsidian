"""Synthesize Obsidian topic pages from collector caches."""

from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel

from scripts.classify.classify_vault import _strip_frontmatter
from scripts.classify.collect_topic import collect_topic, topic_cache_path
from scripts.classify.frontmatter import read_frontmatter
from scripts.classify.lm_classifier import LM_STUDIO_MODEL, _get_client
from scripts.classify.structured_output import generate_structured
from scripts.classify.synthesis_prompt import SYSTEM_PROMPT, build_user_prompt
from scripts.classify.topics import Topic, load_topics
from scripts.classify.wiki_io import append_log, replace_generated_region, upsert_index_line


class TopicSynthesis(BaseModel):
    summary: str
    timeline: str
    key_facts: str
    contradictions: str
    open_questions: str


@dataclass(frozen=True)
class SynthesisResult:
    slug: str
    status: str
    prompt_degraded: bool = False
    source_count: int = 0


_SOURCE_RE = re.compile(r"\(src:\s*B(\d+)\)")
_WIKILINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]")
_SENTENCE_RE = re.compile(
    r".*?[.!?](?:\s*\(src:\s*B\d+\))?(?=\s+|$)|.+$",
    re.MULTILINE,
)


def compute_confidence(*, source_count: int, quality: float) -> float:
    if source_count <= 0:
        return 0.0
    bounded_quality = max(0.0, min(float(quality), 1.0))
    return min(source_count / 3, 1) * 0.5 + 0.5 * bounded_quality


def synthesize_topic(
    *,
    vault: Path,
    topic_slug: str,
    client: Any | None = None,
    json_out: Path = Path("scripts/classify/.topic_cache"),
    force: bool = False,
    dry_run: bool = False,
) -> SynthesisResult:
    topic = _find_topic(vault, topic_slug)
    cache_path = topic_cache_path(vault=vault, slug=topic.slug, json_out=json_out)
    if not cache_path.exists():
        if dry_run:
            with tempfile.TemporaryDirectory() as tmpdir:
                cache_path = collect_topic(
                    vault=vault,
                    topic=topic,
                    json_out=Path(tmpdir),
                )
                return _synthesize_from_cache(
                    vault=vault,
                    topic=topic,
                    cache_path=cache_path,
                    client=client,
                    force=force,
                    dry_run=dry_run,
                )
        cache_path = collect_topic(vault=vault, topic=topic, json_out=json_out)

    return _synthesize_from_cache(
        vault=vault,
        topic=topic,
        cache_path=cache_path,
        client=client,
        force=force,
        dry_run=dry_run,
    )


def _synthesize_from_cache(
    *,
    vault: Path,
    topic: Topic,
    cache_path: Path,
    client: Any | None,
    force: bool,
    dry_run: bool,
) -> SynthesisResult:

    cache = json.loads(cache_path.read_text(encoding="utf-8"))
    sources = list(cache.get("sources", []))
    if not sources:
        if not dry_run:
            append_log(vault, f"{topic.slug}: skipped, zero sources")
        return SynthesisResult(topic.slug, "skipped-zero-sources", source_count=0)

    current_fm = read_frontmatter(topic.path)
    if current_fm.get("source_set_hash") == cache.get("source_set_hash") and not force:
        return SynthesisResult(topic.slug, "skipped-unchanged", source_count=len(sources))

    ranked_sources = _rank_sources(sources)
    prompt_sources, prompt_degraded = _prompt_sources(
        vault=vault,
        cache_sources=ranked_sources,
        ctx=int(os.environ.get("LMSTUDIO_CTX", "8192")),
    )
    whitelist = _link_whitelist(vault)
    schema_excerpt = _schema_excerpt(vault)
    prompt = build_user_prompt(
        topic_slug=topic.slug,
        aliases=topic.aliases,
        schema_excerpt=schema_excerpt,
        link_whitelist=whitelist,
        sources=prompt_sources,
    )

    model_result = generate_structured(
        client=client or _get_client(),
        model=LM_STUDIO_MODEL,
        system=SYSTEM_PROMPT,
        prompt=prompt,
        output_model=TopicSynthesis,
    )

    generated = assemble_generated_markdown(
        synthesis=model_result,
        sources=ranked_sources,
        whitelist=set(whitelist),
    )
    fm = _frontmatter_fields(
        topic=topic,
        cache=cache,
        sources=ranked_sources,
        prompt_degraded=prompt_degraded,
    )
    summary_line = _summary_line(model_result.summary)

    if dry_run:
        print(
            f"dry-run: {topic.slug} would write {len(sources)} sources "
            f"(prompt_degraded={prompt_degraded})"
        )
        return SynthesisResult(
            topic.slug,
            "dry-run",
            prompt_degraded=prompt_degraded,
            source_count=len(sources),
        )

    new_text = _merge_frontmatter_and_body(topic.path, fm, generated)
    _atomic_write(topic.path, new_text)
    append_log(vault, f"{topic.slug}: synthesized {len(sources)} sources")
    upsert_index_line(vault, topic.slug, summary_line)
    return SynthesisResult(
        topic.slug,
        "wrote",
        prompt_degraded=prompt_degraded,
        source_count=len(sources),
    )


def assemble_generated_markdown(
    *,
    synthesis: TopicSynthesis,
    sources: list[dict[str, Any]],
    whitelist: set[str],
) -> str:
    inferences: list[str] = []
    parts = [
        "## Summary",
        _verified_section(synthesis.summary, len(sources), whitelist, inferences),
        "## Timeline",
        _verified_section(synthesis.timeline, len(sources), whitelist, inferences),
        "## Key facts",
        _verified_section(synthesis.key_facts, len(sources), whitelist, inferences),
    ]

    if synthesis.contradictions.strip():
        contradiction = _verified_section(
            synthesis.contradictions,
            len(sources),
            whitelist,
            inferences,
        )
        if contradiction:
            parts.extend(["> [!contradiction]", f"> {contradiction}"])

    parts.extend(
        [
            "## Open questions",
            _verified_section(synthesis.open_questions, len(sources), whitelist, inferences),
        ]
    )
    if inferences:
        parts.extend(["## Inferences (not in the source)", "\n".join(inferences)])
    parts.extend(["## Source blocks", _source_blocks(sources)])
    return "\n\n".join(part for part in parts if part != "") + "\n"


def _find_topic(vault: Path, slug: str) -> Topic:
    for topic in load_topics(vault):
        if topic.slug == slug:
            return topic
    raise ValueError(f"unknown topic: {slug}")


def _rank_sources(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        sources,
        key=lambda source: (
            str(source.get("mtime", "")),
            len(source.get("matched_aliases") or []) + len(source.get("quotes") or []),
        ),
        reverse=True,
    )


def _prompt_sources(*, vault: Path, cache_sources: list[dict[str, Any]], ctx: int) -> tuple[list[dict], bool]:
    budgets = [max(ctx // divisor, 1) for divisor in (2, 4, 8, 16)]
    full_sources = [_source_with_text(vault, source) for source in cache_sources]
    original_total = sum(len(source["text"]) for source in full_sources)
    if original_total <= budgets[0]:
        return full_sources, False

    for idx, budget in enumerate(budgets):
        if idx == 0:
            continue
        trimmed = _trim_sources(full_sources, budget)
        total = sum(len(source["text"]) for source in trimmed)
        if total <= budget or idx == len(budgets) - 1:
            return trimmed, True
    return full_sources, False


def _source_with_text(vault: Path, source: dict[str, Any]) -> dict[str, str]:
    path = vault / source["path"]
    text = _strip_frontmatter(path.read_text(encoding="utf-8")) if path.exists() else ""
    return {
        "title": str(source.get("title") or path.stem),
        "path": str(source.get("path") or path.name),
        "text": " ".join(text.split()),
    }


def _trim_sources(sources: list[dict[str, str]], budget: int) -> list[dict[str, str]]:
    if not sources:
        return []
    per_source = max(budget // len(sources), 1)
    return [{**source, "text": source["text"][:per_source]} for source in sources]


def _link_whitelist(vault: Path) -> list[str]:
    wiki = vault / "wiki"
    if not wiki.exists():
        return []
    return sorted(path.stem for path in wiki.rglob("*.md"))


def _schema_excerpt(vault: Path) -> str:
    schema = vault / "wiki" / "SCHEMA.md"
    return schema.read_text(encoding="utf-8") if schema.exists() else ""


def _verified_section(
    text: str,
    source_count: int,
    whitelist: set[str],
    inferences: list[str],
) -> str:
    kept: list[str] = []
    for sentence in _split_claims(text):
        cleaned = _strip_unknown_wikilinks(sentence.strip(), whitelist)
        if not cleaned:
            continue
        refs = [int(match) for match in _SOURCE_RE.findall(cleaned)]
        if refs and all(1 <= ref <= source_count for ref in refs):
            kept.append(cleaned)
        else:
            inferences.append(cleaned)
    return "\n".join(kept)


def _split_claims(text: str) -> list[str]:
    lines = [line.rstrip() for line in text.strip().splitlines() if line.strip()]
    claims: list[str] = []
    for line in lines:
        prefix = ""
        body = line
        bullet = re.match(r"^(\s*[-*]\s+)(.*)$", line)
        if bullet:
            prefix = bullet.group(1)
            body = bullet.group(2)
        matches = [match.group(0).strip() for match in _SENTENCE_RE.finditer(body)]
        if matches:
            claims.extend(f"{prefix}{match}" for match in matches)
        else:
            claims.append(line)
    return claims


def _strip_unknown_wikilinks(text: str, whitelist: set[str]) -> str:
    def replace(match: re.Match[str]) -> str:
        target = match.group(1)
        label = match.group(2) or target
        return match.group(0) if target in whitelist else label

    return _WIKILINK_RE.sub(replace, text)


def _source_blocks(sources: list[dict[str, Any]]) -> str:
    lines = []
    for idx, source in enumerate(sources, start=1):
        title = str(source.get("title") or Path(source.get("path", "")).stem)
        mtime = str(source.get("mtime") or "")
        quote = _first_quote(source)
        lines.append(f'- B{idx} — [[{title}]] ({mtime}) — "{quote}"')
    return "\n".join(lines)


def _first_quote(source: dict[str, Any]) -> str:
    quotes = source.get("quotes") or []
    if not quotes:
        return ""
    return " ".join(str(quotes[0]).split())


def _frontmatter_fields(
    *,
    topic: Topic,
    cache: dict[str, Any],
    sources: list[dict[str, Any]],
    prompt_degraded: bool,
) -> dict[str, Any]:
    quality = _source_quality(sources)
    return {
        "slug": topic.slug,
        "status": topic.status,
        "sources": [f"[[{source.get('title') or Path(source.get('path', '')).stem}]]" for source in sources],
        "source_set_hash": cache.get("source_set_hash"),
        "confidence": compute_confidence(source_count=len(sources), quality=quality),
        "prompt_degraded": prompt_degraded,
        "updated": datetime.now().astimezone().date().isoformat(),
    }


def _source_quality(sources: list[dict[str, Any]]) -> float:
    if not sources:
        return 0.0
    quote_ratio = sum(1 for source in sources if source.get("quotes")) / len(sources)
    match_ratio = sum(
        min(len(source.get("matched_aliases") or []), 2) / 2 for source in sources
    ) / len(sources)
    return max(0.0, min((quote_ratio + match_ratio) / 2, 1.0))


def _merge_frontmatter_and_body(
    path: Path, new_fields: dict[str, Any], generated: str
) -> str:
    text = path.read_text(encoding="utf-8")
    fm, body = _split_frontmatter(text)
    fm.update(new_fields)
    yaml_block = yaml.safe_dump(
        fm,
        sort_keys=False,
        default_flow_style=None,
        allow_unicode=True,
    )
    new_body = replace_generated_region(body.lstrip("\n"), generated)
    return f"---\n{yaml_block}---\n\n{new_body}"


def _split_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---", 4)
    if end == -1:
        return {}, text
    raw = text[4:end]
    body = text[end + len("\n---") :]
    parsed = yaml.safe_load(raw) or {}
    return parsed if isinstance(parsed, dict) else {}, body


def _summary_line(summary: str) -> str:
    for claim in _split_claims(summary):
        clean = _SOURCE_RE.sub("", claim).strip()
        clean = re.sub(r"\s+", " ", clean)
        if clean:
            return clean
    return "Synthesized topic"


def _atomic_write(path: Path, text: str) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def main(argv: list[str] | None = None, *, client: Any | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--vault", type=Path, required=True)
    parser.add_argument("--topic")
    parser.add_argument("--all", action="store_true", dest="all_topics")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json-out", type=Path, default=Path("scripts/classify/.topic_cache"))
    args = parser.parse_args(argv)

    if bool(args.topic) == args.all_topics:
        parser.error("pass exactly one of --topic or --all")

    slugs = [topic.slug for topic in load_topics(args.vault)] if args.all_topics else [args.topic]
    for slug in slugs:
        result = synthesize_topic(
            vault=args.vault,
            topic_slug=slug,
            client=client,
            json_out=args.json_out,
            force=args.force,
            dry_run=args.dry_run,
        )
        print(f"{result.slug}: {result.status}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
