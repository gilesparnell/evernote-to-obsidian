"""Sample N random auto-classified notes for spot-checking.

Used after each classification run to validate quality before deciding to
proceed (pilot → AWS, AWS → migration, etc.). Reuses the shared skip-list
from `classify_vault._iter_md_files`, so hand-curated content (wiki/) and
backup snapshots (Personal-backup-*/) never surface in samples.

Examples:
    # Spot-check the Job Hunt pilot output
    python scripts/classify/sample_classified.py \\
        --vault ~/Documents/ObsidianVault/Personal --folder "Job Hunt"

    # Only Amazon meetings, reproducible
    python scripts/classify/sample_classified.py \\
        --vault ~/Documents/ObsidianVault/Personal \\
        --filter type=meeting --filter org=Amazon --seed 42
"""

from __future__ import annotations

import argparse
import random
import re
import sys
from pathlib import Path
from typing import Any

from scripts.classify.classify_vault import _iter_md_files
from scripts.classify.frontmatter import is_classified, read_frontmatter

DEFAULT_N = 10
_BODY_EXCERPT_CHARS = 200
_FRONTMATTER_STRIP_RE = re.compile(r"^---\s*\n.*?\n---\s*\n", re.DOTALL)


def parse_filters(args: list[str]) -> list[tuple[str, str]]:
    """Parse ``--filter field=value`` args into (field, value) tuples."""
    out: list[tuple[str, str]] = []
    for arg in args:
        if "=" not in arg:
            raise SystemExit(
                f"Invalid --filter (expected field=value): {arg!r}"
            )
        field, _, value = arg.partition("=")
        out.append((field.strip(), value.strip()))
    return out


def _matches_filters(
    fm: dict[str, Any], filters: list[tuple[str, str]]
) -> bool:
    """AND-combine filter predicates against frontmatter values.

    Stringifies the frontmatter value so a literal ``type=meeting`` filter
    matches a YAML string value `meeting`.
    """
    for field, value in filters:
        if str(fm.get(field)) != value:
            return False
    return True


def sample_classified(
    vault: Path,
    folder: str | None = None,
    n: int = DEFAULT_N,
    filters: list[tuple[str, str]] | None = None,
    seed: int | None = None,
) -> list[Path]:
    """Return up to N random auto-classified notes matching the filter."""
    candidates: list[Path] = []
    for path in _iter_md_files(vault, folder):
        if not is_classified(path):
            continue
        if filters:
            if not _matches_filters(read_frontmatter(path), filters):
                continue
        candidates.append(path)

    rng = random.Random(seed)
    if n >= len(candidates):
        return candidates
    return rng.sample(candidates, n)


def _strip_frontmatter(text: str) -> str:
    match = _FRONTMATTER_STRIP_RE.match(text)
    return text[match.end():] if match else text


def render_report(samples: list[Path], vault: Path) -> str:
    """Format the sampled notes as a terminal report.

    Uses ANSI dim grey for separators and field labels when stdout is a
    TTY; falls back to plain text when piping to another command or a file.
    """
    if sys.stdout.isatty():
        dim, reset = "\033[2m", "\033[0m"
    else:
        dim, reset = "", ""

    if not samples:
        return "No classified notes matched the filter."

    sep = f"{dim}{'─' * 50}{reset}"
    out: list[str] = []
    total = len(samples)
    for i, path in enumerate(samples, start=1):
        fm = read_frontmatter(path)
        body = _strip_frontmatter(path.read_text(encoding="utf-8")).strip()
        excerpt = body[:_BODY_EXCERPT_CHARS]
        if len(body) > _BODY_EXCERPT_CHARS:
            excerpt += "..."

        try:
            rel = path.relative_to(vault)
        except ValueError:
            rel = path

        out.append(sep)
        out.append(f"[{i}/{total}]  {rel}")
        out.append(
            f"        {dim}type:{reset} {fm.get('type')} "
            f"{dim}|{reset} {dim}org:{reset} {fm.get('org')} "
            f"{dim}|{reset} {dim}context:{reset} {fm.get('context')} "
            f"{dim}|{reset} {dim}conf:{reset} "
            f"{fm.get('classify_confidence', 'n/a')}"
        )
        if fm.get("people"):
            out.append(f"        {dim}people:{reset} {fm['people']}")
        if fm.get("tags"):
            out.append(f"        {dim}tags:{reset} {fm['tags']}")
        out.append(f"        {dim}━━━ first 200 chars of body ━━━{reset}")
        for line in excerpt.splitlines()[:5]:
            out.append(f"        {line}")
    return "\n".join(out)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__.split("\n")[0] if __doc__ else "",
    )
    parser.add_argument("--vault", required=True, type=Path)
    parser.add_argument("--folder", default=None)
    parser.add_argument(
        "--n",
        type=int,
        default=DEFAULT_N,
        help=f"Number of notes to sample (default {DEFAULT_N}).",
    )
    parser.add_argument(
        "--filter",
        action="append",
        default=[],
        help="field=value filter; repeat for AND-combine. "
             "OR/NOT not supported in v1.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Random seed for reproducible sampling.",
    )
    args = parser.parse_args()

    filters = parse_filters(args.filter)
    samples = sample_classified(
        vault=args.vault,
        folder=args.folder,
        n=args.n,
        filters=filters,
        seed=args.seed,
    )

    if len(samples) < args.n and not filters:
        print(
            f"Note: only {len(samples)} classified notes available "
            f"(requested {args.n}).",
            file=sys.stderr,
        )
    print(render_report(samples, args.vault))


if __name__ == "__main__":
    main()
