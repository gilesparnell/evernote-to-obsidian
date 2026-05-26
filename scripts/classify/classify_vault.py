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
from scripts.classify.moc_map import UP_MAP, up_for_type  # noqa: F401 re-exported

CONFIDENCE_THRESHOLD = 0.80
DEFAULT_CHECKPOINT_INTERVAL = 50
ICLOUD_SLEEP_SECONDS = 0.05
MIN_BODY_LENGTH = 50

_FRONTMATTER_STRIP_RE = re.compile(r"^---\s*\n.*?\n---\s*\n", re.DOTALL)
_REVIEW_FILENAME = "classification-review.md"
_REVIEW_HTML_FILENAME = "classification-review.html"
_CHECKPOINT_FILENAME = ".classify_checkpoint.json"
_HEARTBEAT_FILENAME = ".classify_progress.json"
_MANIFEST_FILENAME = ".classify_deleted_manifest.json"
_DELETED_BODY_PREVIEW_CHARS = 50
_AEST = timezone(timedelta(hours=10))  # Australia/Sydney standard time

# Top-level vault directories that the classifier must NEVER touch — protects
# operator-curated content (the wiki/ folder uses a different schema) and
# vault backup snapshots from accidental overwrite. Matched against the FIRST
# path component under the vault, so a file literally named "wiki.md" at the
# vault root is not affected.
_SKIP_TOP_LEVEL_EXACT: frozenset[str] = frozenset({"wiki"})
_SKIP_TOP_LEVEL_PREFIX: tuple[str, ...] = ("Personal-backup",)


def _progress_total(scan_size: int, limit: int | None) -> int:
    """tqdm denominator: track progress toward --limit when one is set,
    otherwise toward the full scan size. Caps at scan_size when the user
    asks for more than is available.
    """
    if limit is None:
        return scan_size
    return min(limit, scan_size)


def _count_already_classified(file_list: list[Path]) -> int:
    """Pre-scan: how many files in the corpus already have R2 frontmatter.

    Used to populate the 'overall corpus progress' postfix on the progress
    bar so chunked runs can show 'overall: X / Y' across sessions.

    Tolerates files that vanished after the directory walk (operator
    triaging the review queue in parallel) — those are silently treated
    as unclassified; the main loop will re-encounter and skip them.
    """
    count = 0
    for p in file_list:
        try:
            if _fm.is_classified(p):
                count += 1
        except FileNotFoundError:
            continue
    return count


def _overall_postfix(processed: int, corpus_size: int) -> str:
    """Format the corpus-progress segment of the tqdm postfix.

    Distinct from the bar's primary %: the bar tracks progress toward
    --limit; this string tracks progress across the whole corpus, which
    is what the operator cares about when chunking multi-hour runs.
    """
    if corpus_size <= 0:
        return f"overall: {processed}/{corpus_size}"
    pct = (processed / corpus_size) * 100
    return f"overall: {processed}/{corpus_size} ({pct:.1f}%)"


def _auto_classify_rate(auto: int, review: int) -> str:
    """Format 'ac:X%' showing what fraction of classification attempts
    cleared the auto-classify threshold (rest went to the review queue).
    Lower over time often means the easier notes are done.
    """
    attempts = auto + review
    if attempts == 0:
        return "ac:-"
    pct = round((auto / attempts) * 100)
    return f"ac:{pct}%"


def _rules_hit_rate(rules_auto: int, total_auto: int) -> str:
    """Format 'rules:X%' showing what fraction of auto-classified notes
    came from the rules cascade (no LM call) vs. an LM call. Higher means
    the rules are pulling weight; very low means most work still hits LM.
    """
    if total_auto == 0:
        return "rules:-"
    pct = round((rules_auto / total_auto) * 100)
    return f"rules:{pct}%"


def _corpus_eta(elapsed_seconds: float, attempts: int, remaining: int) -> str:
    """Format 'corpus-eta:Xh' / 'Xm' — projected wall time to classify
    the rest of the unclassified corpus at the current observed rate.

    Uses sec-per-attempt as the baseline. Reported in hours when >= 1h,
    minutes otherwise. Returns '?' if no data yet.
    """
    if attempts == 0 or elapsed_seconds == 0:
        return "corpus-eta:?"
    if remaining <= 0:
        return "corpus-eta:0m"
    sec_per_attempt = elapsed_seconds / attempts
    remaining_seconds = sec_per_attempt * remaining
    if remaining_seconds >= 3600:
        return f"corpus-eta:{remaining_seconds / 3600:.1f}h"
    return f"corpus-eta:{int(remaining_seconds / 60)}m"


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
    skipped_missing: int = 0,
    purged: int = 0,
) -> None:
    """Atomically write a heartbeat snapshot to vault/.classify_progress.json.

    Non-blocking monitoring: any session can ``cat`` this file to see the
    current run's progress. Best-effort — write failures are intentionally
    NOT raised because losing a heartbeat shouldn't crash classification.
    """
    scanned = (
        auto_classified + needs_review
        + skipped_already_classified + skipped_missing + purged
    )
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
            "skipped_missing": skipped_missing,
            "purged": purged,
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


def _update_postfix(
    pbar: tqdm,
    auto_classified: int,
    review_len: int,
    skipped_already_classified: int,
    skipped_missing: int,
    purged: int,
    rules_auto_classified: int,
    lm_latencies: list[float],
    corpus_classified_at_start: int,
    corpus_size: int,
    unclassified_count: int,
    loop_start_seconds: float,
) -> None:
    """Render the tqdm progress-bar postfix string. Extracted so the purge
    branch and the classify branch share one source of truth for the
    counters segment."""
    lm_avg_str = (
        f"lm-avg:{sum(lm_latencies) / len(lm_latencies):.1f}s"
        if lm_latencies else "lm-avg:-"
    )
    attempts = auto_classified + review_len + purged
    corpus_remaining = max(0, unclassified_count - attempts)
    elapsed = time.monotonic() - loop_start_seconds
    pbar.set_postfix_str(
        f"auto:{auto_classified} | review:{review_len} | "
        f"purged:{purged} | "
        f"skip:{skipped_already_classified} | missing:{skipped_missing} | "
        f"{_auto_classify_rate(auto_classified, review_len)} | "
        f"{_rules_hit_rate(rules_auto_classified, auto_classified)} | "
        f"{lm_avg_str} | "
        f"{_overall_postfix(corpus_classified_at_start + auto_classified, corpus_size)} | "
        f"{_corpus_eta(elapsed, attempts, corpus_remaining)}"
    )


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


def _append_deletion_manifest(
    vault: Path, run_id: str, md_path: Path, body: str
) -> None:
    """Append a deletion record to .classify_deleted_manifest.json.

    Atomic tmp+rename write per the project's iCloud-safe pattern. The
    manifest is read first, the new entry is appended, the whole thing is
    rewritten — so deletions accumulate across runs rather than being
    overwritten. The file is created with an empty ``deleted`` list on
    first write.

    Path is stored relative to the vault root so the manifest stays
    portable if the vault is moved or shared.
    """
    target = vault / _MANIFEST_FILENAME
    if target.exists():
        try:
            data = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            # Corrupt manifest — start fresh; better than crashing the run.
            data = {"deleted": []}
    else:
        data = {"deleted": []}

    try:
        rel_path = str(md_path.relative_to(vault))
    except ValueError:
        rel_path = str(md_path)

    body_preview = body[:_DELETED_BODY_PREVIEW_CHARS].replace("\n", " ").strip()
    stripped_chars = len(
        rules_classifier._BODY_STRIP_MARKDOWN_RE.sub("", body).strip()
    )

    data["deleted"].append({
        "path": rel_path,
        "stripped_body_chars": stripped_chars,
        "body_preview": body_preview,
        "deleted_at_aest": _now_aest_iso(),
        "run_id": run_id,
    })

    tmp = target.with_name(target.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.replace(target)


def classify_vault(  # noqa: PLR0913 (caller-driven flag surface)
    vault: Path,
    folder: str | None = None,
    dry_run: bool = False,
    limit: int | None = None,
    checkpoint_interval: int = DEFAULT_CHECKPOINT_INTERVAL,
    html_out: bool = False,
) -> dict[str, Any]:
    """Run classification across the vault. Returns a summary dict."""
    review_queue: list[dict[str, Any]] = []
    processed_paths: list[str] = []
    auto_classified = 0
    skipped_already_classified = 0
    skipped_missing = 0
    purged = 0
    started_at = _now_aest_iso()
    run_id = started_at

    checkpoint_path = vault / _CHECKPOINT_FILENAME

    file_list = list(_iter_md_files(vault, folder))
    corpus_size = len(file_list)
    # Pre-scan so the postfix can report "overall corpus progress" across
    # chunked runs. ~3 sec for a 6,375-note folder; trivial vs. an hours-long
    # classification run.
    corpus_classified_at_start = _count_already_classified(file_list)
    unclassified_count = corpus_size - corpus_classified_at_start
    lm_latencies: list[float] = []
    rules_auto_classified = 0
    loop_start_seconds = time.monotonic()

    # Manual tqdm: total = unclassified notes (capped at --limit). Bar advances
    # only on classification ATTEMPTS, not on already-classified skips. This
    # makes '68%' mean '68% of chunk done', not '68% through file_list'.
    pbar = tqdm(
        total=_progress_total(unclassified_count, limit),
        desc="Classifying",
        unit="note",
        file=sys.stdout,
    )

    for md_path in file_list:
        attempts_so_far = auto_classified + len(review_queue) + purged
        if limit is not None and attempts_so_far >= limit:
            break

        try:
            if _fm.is_classified(md_path):
                skipped_already_classified += 1
                continue
            text = md_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            # The file was in the directory walk's output but has since
            # vanished — typically because the operator is triaging the
            # review queue in parallel and deleted or renamed it. Skip
            # and keep going; a 6,000-note batch must not abort on one
            # missing file.
            skipped_missing += 1
            continue

        body = _strip_frontmatter(text).strip()
        title = md_path.stem
        folder_hint = md_path.parent.name
        processed_paths.append(str(md_path))

        # Step 1 — rules cascade. Body-shape rules inside rules_classifier
        # catch clipping-shape bodies (image/url/embed) with high
        # confidence and short-circuit the LM. Title rules + keyword
        # scoring handle the rest.
        rules_result = rules_classifier.classify(
            title, body, folder_hint=folder_hint,
        )
        lm_latency: float | None = None

        if rules_result["confidence"] >= CONFIDENCE_THRESHOLD:
            chosen = rules_result
            rules_won = True
        else:
            # Step 2 — purge gate. Tiny bodies that the rules cascade
            # couldn't classify confidently are import junk. Hard-delete +
            # manifest, then skip the LM entirely. The ordering matters:
            # by checking rules FIRST, image-only short bodies survive
            # because the clipping rule returns conf 0.85 → auto-classify
            # instead of hitting this purge gate.
            if rules_classifier.should_purge_by_body_shape(body):
                if not dry_run:
                    _append_deletion_manifest(vault, run_id, md_path, body)
                    md_path.unlink()
                    time.sleep(ICLOUD_SLEEP_SECONDS)
                purged += 1
                pbar.update(1)
                _update_postfix(
                    pbar, auto_classified, len(review_queue),
                    skipped_already_classified, skipped_missing, purged,
                    rules_auto_classified, lm_latencies,
                    corpus_classified_at_start, corpus_size,
                    unclassified_count, loop_start_seconds,
                )
                continue

            # Step 3 — LM fallback. Body has real content but the rules
            # cascade couldn't reach the auto-classify threshold.
            t0 = time.perf_counter()
            lm_result = lm_classifier.classify(title, body, folder_hint)
            lm_latency = time.perf_counter() - t0
            lm_latencies.append(lm_latency)
            chosen = (
                lm_result
                if lm_result["confidence"] > rules_result["confidence"]
                else rules_result
            )
            rules_won = False

        if chosen["confidence"] >= CONFIDENCE_THRESHOLD:
            new_fields = {
                "type": chosen["type"],
                "org": chosen["org"],
                "context": chosen["context"],
                "people": chosen["people"],
                "tags": chosen["tags"],
                "up": up_for_type(chosen["type"]),
                "classify_confidence": round(chosen["confidence"], 2),
            }
            if not dry_run:
                _fm.write_frontmatter(md_path, new_fields)
                time.sleep(ICLOUD_SLEEP_SECONDS)
            auto_classified += 1
            if rules_won:
                rules_auto_classified += 1
        elif len(body) < MIN_BODY_LENGTH:
            # Short body that escaped both the clipping rules and the
            # purge gate (30 <= stripped chars < 50). Preserve the
            # historical "too short to classify" review-queue label so
            # operators can still find these via the existing reason.
            review_queue.append({
                "path": md_path,
                "proposed_type": "?",
                "proposed_org": "?",
                "confidence": 0.0,
                "reason": "too short to classify",
            })
        else:
            review_queue.append({
                "path": md_path,
                "proposed_type": chosen["type"],
                "proposed_org": chosen["org"],
                "confidence": chosen["confidence"],
                "reason": chosen.get(
                    "reason", "low confidence from both classifiers"
                ),
            })

        pbar.update(1)  # advance on classification attempt only

        _update_postfix(
            pbar, auto_classified, len(review_queue),
            skipped_already_classified, skipped_missing, purged,
            rules_auto_classified, lm_latencies,
            corpus_classified_at_start, corpus_size,
            unclassified_count, loop_start_seconds,
        )

        if not dry_run and len(processed_paths) % checkpoint_interval == 0:
            checkpoint_path.write_text(
                json.dumps(processed_paths), encoding="utf-8"
            )
            _write_heartbeat(
                vault, folder, started_at,
                auto_classified, len(review_queue), skipped_already_classified,
                lm_latencies, complete=False,
                skipped_missing=skipped_missing,
                purged=purged,
            )

    pbar.close()

    if not dry_run:
        _write_heartbeat(
            vault, folder, started_at,
            auto_classified, len(review_queue), skipped_already_classified,
            lm_latencies, complete=True,
            skipped_missing=skipped_missing,
            purged=purged,
        )

    generated = datetime.now().strftime("%Y-%m-%d")
    review_md = _format_review_queue(review_queue, vault, generated)

    if dry_run:
        print(review_md)
    else:
        (vault / _REVIEW_FILENAME).write_text(review_md, encoding="utf-8")
        if html_out:
            from scripts.classify.html_renderer import render_review_queue_html
            review_html = render_review_queue_html(
                review_queue, vault, generated
            )
            (vault / _REVIEW_HTML_FILENAME).write_text(
                review_html, encoding="utf-8"
            )

    return {
        "auto_classified": auto_classified,
        "skipped_already_classified": skipped_already_classified,
        "skipped_missing": skipped_missing,
        "purged": purged,
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
    parser.add_argument(
        "--html", action="store_true",
        help="Also write classification-review.html alongside the .md "
             "(self-contained, opens in any browser, links straight into "
             "Obsidian via obsidian:// URLs).",
    )
    args = parser.parse_args()

    summary = classify_vault(
        vault=args.vault,
        folder=args.folder,
        dry_run=args.dry_run,
        limit=args.limit,
        html_out=args.html,
    )
    purge_label = (
        f"purged={summary['purged']} (dry-run, no files removed)"
        if args.dry_run
        else f"purged={summary['purged']}"
    )
    print(
        f"\nauto_classified={summary['auto_classified']}, "
        f"needs_review={summary['needs_review']}, "
        f"{purge_label}, "
        f"skipped_already_classified={summary['skipped_already_classified']}, "
        f"skipped_missing={summary['skipped_missing']}"
    )


if __name__ == "__main__":
    main()
