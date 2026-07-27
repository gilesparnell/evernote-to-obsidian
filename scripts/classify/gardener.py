"""Build and write the nightly gardener report."""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Allow direct script invocation from future orchestrator/panel entry points.
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.classify.classify_vault import _iter_md_files
from scripts.classify.frontmatter import is_classified, read_frontmatter
from scripts.classify.topics import load_topics
from scripts.classify.wiki_io import replace_generated_region


HEALTH_SCORE_WEIGHTS = {
    "run_complete": 20,
    "coverage": 35,
    "no_orphans": 15,
    "no_review_queue": 10,
    "no_exhaust": 10,
    "fresh_topics": 10,
}

_REVIEW_QUEUE_NAME = "classification-review.md"
_EXHAUST_RE = re.compile(r"^classification-review.*\.html$")


@dataclass(frozen=True)
class _VaultMetrics:
    name: str
    classified: int
    total: int
    coverage_ratio: float
    unclassified: int
    orphan_count: int
    review_queue_count: int
    exhaust_files: list[Path]


@dataclass(frozen=True)
class _TopicFreshness:
    vault: str
    slug: str
    source_count: int | None
    last_synthesis: str | None
    hash_changed: bool | None


def build_report(*, vaults: list[Path], run_state: dict, json_out: Path) -> str:
    """Return the generated markdown body for the rolling gardener report."""
    metrics = [_vault_metrics(vault) for vault in vaults]
    freshness = [
        row
        for vault in vaults
        for row in _topic_freshness(vault=vault, json_out=json_out)
    ]
    topic_count = len(freshness)
    stale_topic_count = sum(1 for row in freshness if row.hash_changed is True)
    total_notes = sum(item.total for item in metrics)
    total_classified = sum(item.classified for item in metrics)
    coverage_ratio = total_classified / total_notes if total_notes else 1.0
    health = _health_score(
        run_complete=run_state.get("complete") is True,
        coverage_ratio=coverage_ratio,
        orphan_count=sum(item.orphan_count for item in metrics),
        review_queue_count=sum(item.review_queue_count for item in metrics),
        exhaust_count=sum(len(item.exhaust_files) for item in metrics),
        stale_topic_count=stale_topic_count,
        topic_count=topic_count,
    )

    parts = [
        "# Gardener",
        "",
        f"Health score: {health}/100",
        "",
        "## Last run",
        "",
        "| Field | Value |",
        "|---|---|",
        f"| Started | {_display(run_state.get('started_at'))} |",
        f"| Mode | {_display(run_state.get('mode'))} |",
        f"| Complete | {_display_bool(run_state.get('complete'))} |",
        f"| LM Studio | {_display_lm_studio(run_state.get('lm_studio'))} |",
        "",
        "| Step | Status | Detail |",
        "|---|---|---|",
        *_run_step_rows(run_state),
        "",
        "## Vault coverage",
        "",
        "| Vault | Classified | Coverage | Unclassified | Orphan up | Queue | Exhaust |",
        "|---|---:|---:|---:|---:|---:|---:|",
        *[_vault_row(item) for item in metrics],
        "",
        "## Machine exhaust",
        "",
        *_exhaust_lines(metrics),
        "",
        "## Topic freshness",
        "",
        "| Vault | Topic | Sources | Last synthesis | Hash changed |",
        "|---|---|---:|---|---|",
        *[_freshness_row(row) for row in freshness],
        "",
        "## Proposals",
        "",
        "Topic proposer is pending U6.",
    ]
    return "\n".join(parts).rstrip() + "\n"


def write_report(*, vault: Path, report_md: str, dry_run: bool = False) -> None:
    """Write Personal/wiki/gardener.md, replacing only the generated region."""
    path = vault / "wiki" / "gardener.md"
    existing = path.read_text(encoding="utf-8") if path.exists() else _empty_report()
    updated = replace_generated_region(existing, report_md)

    if dry_run:
        return

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(updated, encoding="utf-8")
    tmp.replace(path)


def _health_score(
    *,
    run_complete: bool,
    coverage_ratio: float,
    orphan_count: int,
    review_queue_count: int,
    exhaust_count: int,
    stale_topic_count: int,
    topic_count: int,
) -> int:
    score = 0.0
    if run_complete:
        score += HEALTH_SCORE_WEIGHTS["run_complete"]
    score += HEALTH_SCORE_WEIGHTS["coverage"] * max(0.0, min(coverage_ratio, 1.0))
    if orphan_count == 0:
        score += HEALTH_SCORE_WEIGHTS["no_orphans"]
    if review_queue_count == 0:
        score += HEALTH_SCORE_WEIGHTS["no_review_queue"]
    if exhaust_count == 0:
        score += HEALTH_SCORE_WEIGHTS["no_exhaust"]
    if topic_count == 0 or stale_topic_count == 0:
        score += HEALTH_SCORE_WEIGHTS["fresh_topics"]
    return max(0, min(100, round(score)))


def _vault_metrics(vault: Path) -> _VaultMetrics:
    files = list(_iter_md_files(vault, None))
    classified = sum(1 for path in files if _safe_is_classified(path))
    total = len(files)
    unclassified = total - classified
    return _VaultMetrics(
        name=vault.name,
        classified=classified,
        total=total,
        coverage_ratio=classified / total if total else 1.0,
        unclassified=unclassified,
        orphan_count=_orphan_count(vault, files),
        review_queue_count=_review_queue_count(vault),
        exhaust_files=_exhaust_files(vault),
    )


def _safe_is_classified(path: Path) -> bool:
    try:
        return is_classified(path)
    except OSError:
        return False


def _orphan_count(vault: Path, files: list[Path]) -> int:
    orphans = 0
    for path in files:
        fm = read_frontmatter(path)
        up = fm.get("up")
        if not isinstance(up, str) or not up.strip():
            continue
        if not _up_target_exists(vault=vault, current=path, up=up.strip()):
            orphans += 1
    return orphans


def _up_target_exists(*, vault: Path, current: Path, up: str) -> bool:
    candidates = [up]
    if up.startswith("[[") and up.endswith("]]"):
        candidates.append(up[2:-2].split("|", 1)[0])
    for candidate in candidates:
        relative = candidate[:-3] if candidate.endswith(".md") else candidate
        if (vault / f"{relative}.md").exists():
            return True
        if (current.parent / f"{relative}.md").exists():
            return True
    return False


def _review_queue_count(vault: Path) -> int:
    path = vault / _REVIEW_QUEUE_NAME
    if not path.exists():
        return 0
    lines = [
        line
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    if lines and lines[0].startswith("|"):
        return sum(1 for line in lines if line.startswith("| [["))
    return len(lines)


def _exhaust_files(vault: Path) -> list[Path]:
    return sorted(
        (
            path.resolve()
            for path in vault.iterdir()
            if path.is_file() and _EXHAUST_RE.match(path.name)
        ),
        key=lambda path: path.name,
    )


def _topic_freshness(*, vault: Path, json_out: Path) -> list[_TopicFreshness]:
    rows: list[_TopicFreshness] = []
    for topic in load_topics(vault):
        cache = json_out / f"{vault.name}-{topic.slug}.json"
        cache_data = _read_json(cache) if cache.exists() else {}
        topic_fm = read_frontmatter(topic.path)
        source_count = _source_count(cache_data)
        topic_hash = topic_fm.get("source_set_hash")
        cache_hash = cache_data.get("source_set_hash")
        rows.append(
            _TopicFreshness(
                vault=vault.name,
                slug=topic.slug,
                source_count=source_count,
                last_synthesis=_string_or_none(topic_fm.get("updated")),
                hash_changed=(
                    None
                    if not isinstance(cache_hash, str) or not isinstance(topic_hash, str)
                    else cache_hash != topic_hash
                ),
            )
        )
    return rows


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _source_count(data: dict[str, Any]) -> int | None:
    sources = data.get("sources")
    return len(sources) if isinstance(sources, list) else None


def _display_lm_studio(status: object) -> str:
    if not isinstance(status, dict):
        return "n/a"
    if status.get("available") is True:
        models = ", ".join(status.get("models") or []) or "no models listed"
        return f"available ({models})"
    reason = status.get("reason") or "unknown reason"
    return f"NOT AVAILABLE — {reason}"


def _run_step_rows(run_state: dict) -> list[str]:
    steps = run_state.get("steps")
    if not isinstance(steps, dict) or not steps:
        return ["| n/a | n/a | n/a |"]
    rows: list[str] = []
    for name, value in steps.items():
        data = value if isinstance(value, dict) else {}
        rows.append(
            f"| {_display(name)} | {_display(data.get('status'))} | "
            f"{_display(data.get('detail'))} |"
        )
    return rows


def _vault_row(metrics: _VaultMetrics) -> str:
    return (
        f"| {metrics.name} | {metrics.classified} / {metrics.total} | "
        f"{metrics.coverage_ratio * 100:.1f}% | {metrics.unclassified} | "
        f"{metrics.orphan_count} | {metrics.review_queue_count} | "
        f"{len(metrics.exhaust_files)} |"
    )


def _exhaust_lines(metrics: list[_VaultMetrics]) -> list[str]:
    lines: list[str] = []
    for item in metrics:
        if not item.exhaust_files:
            lines.append(f"- {item.name}: none")
        else:
            for path in item.exhaust_files:
                lines.append(f"- {item.name}: [{path.name}]({path.as_uri()})")
    return lines


def _freshness_row(row: _TopicFreshness) -> str:
    return (
        f"| {row.vault} | {row.slug} | {_display(row.source_count)} | "
        f"{_display(row.last_synthesis)} | {_display_hash_changed(row.hash_changed)} |"
    )


def _empty_report() -> str:
    return (
        "---\n"
        "type: gardener-report\n"
        "updated: n/a\n"
        "---\n\n"
        "# Gardener\n"
    )


def _display(value: Any) -> str:
    if value is None or value == "":
        return "n/a"
    return str(value).replace("\n", " ")


def _display_bool(value: Any) -> str:
    if value is True:
        return "true"
    if value is False:
        return "false"
    return "n/a"


def _display_hash_changed(value: bool | None) -> str:
    if value is True:
        return "yes"
    if value is False:
        return "no"
    return "n/a"


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)
