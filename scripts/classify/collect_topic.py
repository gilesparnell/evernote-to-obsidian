"""Collect source notes for a synthesis topic.

Scans an Obsidian vault for markdown notes that mention a topic alias and
writes a deterministic JSON cache consumed by later synthesis steps.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Iterator

from scripts.classify.classify_vault import (
    _SKIP_TOP_LEVEL_EXACT,
    _SKIP_TOP_LEVEL_PREFIX,
    _strip_frontmatter,
)
from scripts.classify.frontmatter import read_frontmatter
from scripts.classify.topics import Topic, load_topics


_SMART_APOSTROPHES = str.maketrans({"’": "'", "‘": "'", "‛": "'", "`": "'"})
_SENTENCE_RE = re.compile(r"[^.!?]+[.!?]|[^.!?]+$", re.DOTALL)


def topic_cache_path(*, vault: Path, slug: str, json_out: Path) -> Path:
    return json_out / f"{vault.name}-{slug}.json"


def collect_topic(*, vault: Path, topic: Topic, json_out: Path) -> Path:
    json_out.mkdir(parents=True, exist_ok=True)
    cache_path = topic_cache_path(vault=vault, slug=topic.slug, json_out=json_out)

    sources: list[dict[str, Any]] = []
    hash_pairs: list[tuple[str, str]] = []

    for path in _iter_source_notes(vault):
        text = path.read_text(encoding="utf-8")
        body = _strip_frontmatter(text)
        rel = path.relative_to(vault).as_posix()

        matched_aliases = _matched_aliases(
            aliases=topic.aliases,
            filename=path.name,
            body=body,
        )
        if not matched_aliases:
            continue

        fm = read_frontmatter(path)
        title = fm.get("title")
        body_sha = hashlib.sha256(body.encode("utf-8")).hexdigest()
        hash_pairs.append((rel, body_sha))

        sources.append(
            {
                "path": rel,
                "title": title if isinstance(title, str) and title else path.stem,
                "mtime": _mtime_iso(path),
                "matched_aliases": matched_aliases,
                "quotes": _quotes(body=body, aliases=topic.aliases),
            }
        )

    data = {
        "slug": topic.slug,
        "vault": str(vault),
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "source_set_hash": _source_set_hash(hash_pairs),
        "sources": sources,
    }
    cache_path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return cache_path


def _iter_source_notes(vault: Path) -> Iterator[Path]:
    for path in sorted(vault.rglob("*.md")):
        rel_parts = path.relative_to(vault).parts
        if any(part.startswith(".") for part in rel_parts):
            continue
        if rel_parts and rel_parts[0] in _SKIP_TOP_LEVEL_EXACT:
            continue
        if rel_parts and any(
            rel_parts[0].startswith(prefix) for prefix in _SKIP_TOP_LEVEL_PREFIX
        ):
            continue
        yield path


def _matched_aliases(*, aliases: Iterable[str], filename: str, body: str) -> list[str]:
    haystack = f"{filename}\n{body}"
    folded_haystack = _fold(haystack)
    return [
        alias
        for alias in aliases
        if alias and _alias_pattern(alias).search(folded_haystack)
    ]


def _quotes(*, body: str, aliases: Iterable[str]) -> list[str]:
    patterns = [_alias_pattern(alias) for alias in aliases if alias]
    if not patterns:
        return []

    quotes: list[str] = []
    for match in _SENTENCE_RE.finditer(body):
        sentence = " ".join(match.group(0).split())
        if not sentence:
            continue
        folded_sentence = _fold(sentence)
        if any(pattern.search(folded_sentence) for pattern in patterns):
            quotes.append(sentence)
            if len(quotes) == 4:
                break
    return quotes


def _alias_pattern(alias: str) -> re.Pattern[str]:
    return re.compile(rf"(?<!\w){re.escape(_fold(alias))}(?!\w)")


def _fold(text: str) -> str:
    folded = unicodedata.normalize("NFKD", text.translate(_SMART_APOSTROPHES))
    return folded.casefold()


def _source_set_hash(pairs: Iterable[tuple[str, str]]) -> str:
    h = hashlib.sha256()
    for rel, body_sha in sorted(pairs):
        h.update(rel.encode("utf-8"))
        h.update(b"\0")
        h.update(body_sha.encode("ascii"))
        h.update(b"\n")
    return f"sha256:{h.hexdigest()}"


def _mtime_iso(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime).astimezone().isoformat(
        timespec="seconds"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--vault", type=Path, required=True)
    parser.add_argument("--topic")
    parser.add_argument("--all", action="store_true", dest="all_topics")
    parser.add_argument("--json-out", type=Path, default=Path("scripts/classify/.topic_cache"))
    args = parser.parse_args(argv)

    if bool(args.topic) == args.all_topics:
        parser.error("pass exactly one of --topic or --all")

    topics = load_topics(args.vault)
    if args.topic:
        topics = [topic for topic in topics if topic.slug == args.topic]
        if not topics:
            parser.error(f"unknown topic: {args.topic}")

    for topic in topics:
        cache = collect_topic(vault=args.vault, topic=topic, json_out=args.json_out)
        source_count = len(json.loads(cache.read_text(encoding="utf-8"))["sources"])
        print(f"{topic.slug}: {source_count} sources -> {cache}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
