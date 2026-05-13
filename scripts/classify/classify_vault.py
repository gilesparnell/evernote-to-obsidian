"""Batch classification pipeline — drives rules + LM Studio across a vault.

Per the plan (§Unit 5):
- Iterate .md files in the vault (recursively, scoped to `--folder` if given)
- Skip already-classified notes (frontmatter has the four required R2 fields)
- Skip notes with body < 50 chars → review queue with "too short"
- Run rules_classifier first; if confidence < 0.80, fall back to lm_classifier
- If final confidence ≥ 0.80, write frontmatter atomically
- Otherwise append to the review queue
- Write a JSON checkpoint every `checkpoint_interval` notes
- 50 ms pause between writes to avoid triggering iCloud sync storms

Usage:
    python scripts/classify/classify_vault.py --vault ~/Documents/ObsidianVault/Personal \\
        --folder "Job Hunt" --dry-run --limit 10

Run via the project venv:
    scripts/classify/venv/bin/python scripts/classify/classify_vault.py ...
"""

from __future__ import annotations

import argparse
import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

from scripts.classify import frontmatter as _fm
from scripts.classify import lm_classifier, rules_classifier

CONFIDENCE_THRESHOLD = 0.80
DEFAULT_CHECKPOINT_INTERVAL = 50
ICLOUD_SLEEP_SECONDS = 0.05
MIN_BODY_LENGTH = 50

UP_MAP: dict[str, str] = {
    "meeting": "[[Meetings]]",
    "technical": "[[Technical]]",
    "reference": "[[Reference]]",
    "person": "[[People]]",
    "company": "[[Companies]]",
    "recipe": "[[Personal]]",
    "journal": "[[Personal]]",
    "personal": "[[Personal]]",
    "note": "[[Personal]]",
    "project": "[[Projects]]",
    "interview": "[[Interview Prep]]",
    "management": "[[Leadership]]",
    "application": "[[Job Hunt]]",
    "career": "[[Career]]",
    "pattern": "[[Patterns]]",
}

_FRONTMATTER_STRIP_RE = re.compile(r"^---\s*\n.*?\n---\s*\n", re.DOTALL)
_REVIEW_FILENAME = "classification-review.md"
_CHECKPOINT_FILENAME = ".classify_checkpoint.json"


def up_for_type(type_value: str) -> str:
    """Return the MOC wikilink for a type, falling back to [[Personal]]."""
    return UP_MAP.get(type_value, "[[Personal]]")


def _strip_frontmatter(text: str) -> str:
    match = _FRONTMATTER_STRIP_RE.match(text)
    return text[match.end():] if match else text


def _iter_md_files(vault: Path, folder: str | None) -> Iterator[Path]:
    """Yield .md files under vault (or vault/folder), excluding hidden dirs
    and the review-queue output file itself."""
    root = vault if folder is None else vault / folder
    if not root.exists():
        return
    for path in sorted(root.rglob("*.md")):
        # Skip anything under a hidden directory (.obsidian, .trash, etc.)
        rel_parts = path.relative_to(vault).parts
        if any(part.startswith(".") for part in rel_parts):
            continue
        if path.name == _REVIEW_FILENAME:
            continue
        yield path


def _format_review_queue(
    queue: list[dict[str, Any]], vault: Path, generated: str
) -> str:
    lines = [
        "# Classification Review Queue",
        f"Generated: {generated}",
        f"{len(queue)} notes need manual review.",
        "",
        "| Note | Proposed type | Proposed org | Confidence | Reason |",
        "|------|--------------|-------------|------------|--------|",
    ]
    for item in queue:
        try:
            rel = item["path"].relative_to(vault)
        except ValueError:
            rel = item["path"]
        lines.append(
            f"| [[{rel}]] | {item['proposed_type']} | {item['proposed_org']} | "
            f"{item['confidence']:.2f} | {item['reason']} |"
        )
    return "\n".join(lines) + "\n"


def _classify_note_content(title: str, body: str, folder_hint: str) -> dict[str, Any]:
    """Run rules, then LM Studio fallback when rules confidence is low.

    Keeps whichever classifier produces the higher confidence — never
    downgrades a confident rules result by overwriting it with a worse LM
    output.
    """
    result = rules_classifier.classify(title, body, folder_hint=folder_hint)
    if result["confidence"] >= CONFIDENCE_THRESHOLD:
        return result
    lm_result = lm_classifier.classify(title, body, folder_hint)
    if lm_result["confidence"] > result["confidence"]:
        return lm_result
    return result


def classify_vault(
    vault: Path,
    folder: str | None = None,
    dry_run: bool = False,
    limit: int | None = None,
    checkpoint_interval: int = DEFAULT_CHECKPOINT_INTERVAL,
) -> dict[str, Any]:
    """Run classification across the vault. Returns a summary dict."""
    review_queue: list[dict[str, Any]] = []
    processed_paths: list[str] = []
    auto_classified = 0
    skipped_already_classified = 0

    checkpoint_path = vault / _CHECKPOINT_FILENAME

    for md_path in _iter_md_files(vault, folder):
        if limit is not None and (auto_classified + len(review_queue)) >= limit:
            break

        if _fm.is_classified(md_path):
            skipped_already_classified += 1
            continue

        text = md_path.read_text(encoding="utf-8")
        body = _strip_frontmatter(text).strip()
        title = md_path.stem
        folder_hint = md_path.parent.name
        processed_paths.append(str(md_path))

        if len(body) < MIN_BODY_LENGTH:
            review_queue.append({
                "path": md_path,
                "proposed_type": "?",
                "proposed_org": "?",
                "confidence": 0.0,
                "reason": "too short to classify",
            })
        else:
            result = _classify_note_content(title, body, folder_hint)
            if result["confidence"] >= CONFIDENCE_THRESHOLD:
                new_fields = {
                    "type": result["type"],
                    "org": result["org"],
                    "context": result["context"],
                    "people": result["people"],
                    "tags": result["tags"],
                    "up": up_for_type(result["type"]),
                    "classify_confidence": round(result["confidence"], 2),
                }
                if not dry_run:
                    _fm.write_frontmatter(md_path, new_fields)
                    time.sleep(ICLOUD_SLEEP_SECONDS)
                auto_classified += 1
            else:
                review_queue.append({
                    "path": md_path,
                    "proposed_type": result["type"],
                    "proposed_org": result["org"],
                    "confidence": result["confidence"],
                    "reason": result.get(
                        "reason", "low confidence from both classifiers"
                    ),
                })

        if not dry_run and len(processed_paths) % checkpoint_interval == 0:
            checkpoint_path.write_text(
                json.dumps(processed_paths), encoding="utf-8"
            )

    generated = datetime.now().strftime("%Y-%m-%d")
    review_md = _format_review_queue(review_queue, vault, generated)

    if dry_run:
        print(review_md)
    else:
        (vault / _REVIEW_FILENAME).write_text(review_md, encoding="utf-8")

    return {
        "auto_classified": auto_classified,
        "skipped_already_classified": skipped_already_classified,
        "needs_review": len(review_queue),
        "review_queue_md": review_md,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--vault", required=True, type=Path,
                        help="Path to the Obsidian vault root.")
    parser.add_argument("--folder", default=None,
                        help="Restrict processing to a single subfolder.")
    parser.add_argument("--dry-run", action="store_true",
                        help="No files written; review queue printed to stdout.")
    parser.add_argument("--limit", type=int, default=None,
                        help="Process at most N unclassified notes this run.")
    args = parser.parse_args()

    summary = classify_vault(
        vault=args.vault,
        folder=args.folder,
        dry_run=args.dry_run,
        limit=args.limit,
    )
    print(
        f"\nauto_classified={summary['auto_classified']}, "
        f"needs_review={summary['needs_review']}, "
        f"skipped_already_classified={summary['skipped_already_classified']}"
    )


if __name__ == "__main__":
    main()
