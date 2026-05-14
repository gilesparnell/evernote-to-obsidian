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
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

from tqdm import tqdm

# Allow direct script invocation (`python scripts/classify/classify_vault.py`).
# Module invocation (`python -m scripts.classify.classify_vault`) already
# puts the repo root on sys.path; direct invocation does not.
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

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
_HEARTBEAT_FILENAME = ".classify_progress.json"
_AEST = timezone(timedelta(hours=10))  # Australia/Sydney standard time

# Top-level vault directories that the classifier must NEVER touch — protects
# operator-curated content (the wiki/ folder uses a different schema) and
# vault backup snapshots from accidental overwrite. Matched against the FIRST
# path component under the vault, so a file literally named "wiki.md" at the
# vault root is not affected.
_SKIP_TOP_LEVEL_EXACT: frozenset[str] = frozenset({"wiki"})
_SKIP_TOP_LEVEL_PREFIX: tuple[str, ...] = ("Personal-backup",)


def up_for_type(type_value: str) -> str:
    """Return the MOC wikilink for a type, falling back to [[Personal]]."""
    return UP_MAP.get(type_value, "[[Personal]]")


def _strip_frontmatter(text: str) -> str:
    match = _FRONTMATTER_STRIP_RE.match(text)
    return text[match.end():] if match else text


def _iter_md_files(vault: Path, folder: str | None) -> Iterator[Path]:
    """Yield .md files under vault (or vault/folder), excluding hidden dirs,
    operator-curated content (wiki/, Personal-backup-*/), and the
    review-queue output file itself."""
    root = vault if folder is None else vault / folder
    if not root.exists():
        return
    for path in sorted(root.rglob("*.md")):
        rel_parts = path.relative_to(vault).parts
        # Hidden anywhere in the path (.obsidian, .trash, etc.)
        if any(part.startswith(".") for part in rel_parts):
            continue
        # Top-level operator-curated directories — unconditional skip.
        if rel_parts and rel_parts[0] in _SKIP_TOP_LEVEL_EXACT:
            continue
        if rel_parts and any(
            rel_parts[0].startswith(p) for p in _SKIP_TOP_LEVEL_PREFIX
        ):
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


def _now_aest_iso() -> str:
    """Current time as ISO-8601 string with AEST (+10:00) offset.

    DST handling is deliberately deferred — see plan §Deferred to
    Implementation. Acceptable until the next AEDT switch (~Oct 2026).
    """
    return datetime.now(_AEST).isoformat(timespec="seconds")


def _write_heartbeat(
    vault: Path,
    folder: str | None,
    started_at: str,
    auto_classified: int,
    needs_review: int,
    skipped_already_classified: int,
    lm_latencies: list[float],
    complete: bool,
) -> None:
    """Atomically write a heartbeat snapshot to vault/.classify_progress.json.

    Non-blocking monitoring: any session can ``cat`` this file to see the
    current run's progress. Best-effort — write failures are intentionally
    NOT raised because losing a heartbeat shouldn't crash classification.
    """
    scanned = auto_classified + needs_review + skipped_already_classified
    lm_avg = (
        round(sum(lm_latencies) / len(lm_latencies), 1)
        if lm_latencies else 0.0
    )
    data = {
        "started_at": started_at,
        "last_updated": _now_aest_iso(),
        "complete": complete,
        "vault": str(vault),
        "folder": folder,
        "totals": {
            "scanned": scanned,
            "auto_classified": auto_classified,
            "needs_review": needs_review,
            "skipped_already_classified": skipped_already_classified,
            "lm_calls": len(lm_latencies),
            "lm_call_avg_seconds": lm_avg,
        },
    }
    target = vault / _HEARTBEAT_FILENAME
    tmp = target.with_name(target.name + ".tmp")
    try:
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        tmp.replace(target)
    except OSError:
        # Heartbeat is non-load-bearing — don't crash the run.
        pass


def _classify_note_content(
    title: str, body: str, folder_hint: str
) -> tuple[dict[str, Any], float | None]:
    """Run rules, then LM Studio fallback when rules confidence is low.

    Returns ``(result, lm_latency_seconds)``. lm_latency is None when no LM
    call fired (rules already confident); otherwise the wall-clock time of
    the LM call. Used by the progress bar's running average.
    """
    result = rules_classifier.classify(title, body, folder_hint=folder_hint)
    if result["confidence"] >= CONFIDENCE_THRESHOLD:
        return result, None
    t0 = time.perf_counter()
    lm_result = lm_classifier.classify(title, body, folder_hint)
    lm_latency = time.perf_counter() - t0
    if lm_result["confidence"] > result["confidence"]:
        return lm_result, lm_latency
    return result, lm_latency


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
    started_at = _now_aest_iso()

    checkpoint_path = vault / _CHECKPOINT_FILENAME

    file_list = list(_iter_md_files(vault, folder))
    lm_latencies: list[float] = []
    pbar = tqdm(file_list, desc="Classifying", unit="note", file=sys.stdout)

    for md_path in pbar:
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
            result, lm_latency = _classify_note_content(title, body, folder_hint)
            if lm_latency is not None:
                lm_latencies.append(lm_latency)
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

        lm_avg_str = (
            f" | lm-avg:{sum(lm_latencies) / len(lm_latencies):.1f}s"
            if lm_latencies else ""
        )
        pbar.set_postfix_str(
            f"auto:{auto_classified} | review:{len(review_queue)}{lm_avg_str}"
        )

        if not dry_run and len(processed_paths) % checkpoint_interval == 0:
            checkpoint_path.write_text(
                json.dumps(processed_paths), encoding="utf-8"
            )
            _write_heartbeat(
                vault, folder, started_at,
                auto_classified, len(review_queue), skipped_already_classified,
                lm_latencies, complete=False,
            )

    if not dry_run:
        _write_heartbeat(
            vault, folder, started_at,
            auto_classified, len(review_queue), skipped_already_classified,
            lm_latencies, complete=True,
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


_CLI_DESCRIPTION = """\
Classify Obsidian notes into R2 schema (type / org / context / people / tags)
via a rules-first then LM-Studio-fallback cascade. Notes scoring >= 0.80
confidence get frontmatter written in place; lower-confidence notes go
to classification-review.md for manual review.

Progress bar + .classify_progress.json heartbeat make long runs (AWS:
~15 hours) safe to monitor from a separate terminal.
"""

_CLI_EPILOG = """\
Common patterns:

  # Pilot - Job Hunt folder (~35 notes, minutes)
  %(prog)s --vault ~/Documents/ObsidianVault/Personal --folder "Job Hunt"

  # AWS scale-out (~15h overnight), chunked for visible progress
  %(prog)s --vault ~/Documents/ObsidianVault/Personal \\
    --folder "Evernote/notes/AWS" --limit 500

  # Dry run - count what would happen, no writes
  %(prog)s --vault ~/Documents/ObsidianVault/Personal \\
    --folder "Job Hunt" --dry-run

  # Watch progress from a separate terminal
  cat ~/Documents/ObsidianVault/Personal/.classify_progress.json
"""


def main() -> None:
    parser = argparse.ArgumentParser(
        description=_CLI_DESCRIPTION,
        epilog=_CLI_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--vault", required=True, type=Path,
        help="Obsidian vault root (e.g. ~/Documents/ObsidianVault/Personal).",
    )
    parser.add_argument(
        "--folder", default=None,
        help="Restrict to one subfolder. Default: scan the whole vault. "
             "Skip-list (wiki/, Personal-backup-*, hidden dirs) still applies.",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Count what would happen; no frontmatter writes, no checkpoint, "
             "no heartbeat. Review queue printed to stdout instead of file.",
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Stop after processing N unclassified notes (default: no limit).",
    )
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
