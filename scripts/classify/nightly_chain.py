"""Nightly/panel orchestrator for the vault synthesis chain."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Callable, Any

# Allow direct script invocation from launchd/panel.
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.classify.classify_vault import classify_vault
from scripts.classify.lm_classifier import LM_STUDIO_BASE_URL
from scripts.classify.collect_topic import collect_topic
from scripts.classify.gardener import build_report, write_report
from scripts.classify.synthesize_topic import SynthesisResult, synthesize_topic
from scripts.classify.topic_backlinks import BacklinkSummary, reconcile_backlinks
from scripts.classify.topics import Topic, load_topics
from scripts.classify.wiki_io import append_log


_SYSTEM_PY = Path("/opt/homebrew/bin/python3")
_GRANOLA_DIR = _REPO_ROOT.parent / "granolaSync"
_DEFAULT_STATE_DIR = _REPO_ROOT / "scripts" / "classify" / ".chain_state"
_DEFAULT_JSON_OUT = _REPO_ROOT / "scripts" / "classify" / ".topic_cache"
_LOCK_NAME = "nightly_chain.lock"
_EXPORT_TIMEOUT_SECONDS = 900
_PANEL_STEPS = ("classify", "collect", "synthesize", "backlink")
_TRANSIENT_NEEDLES = ("connection", "timeout", "timed out", "unreachable", "refused")
_LM_CHECK_TIMEOUT_SECONDS = 3.0

# Module-level indirection so tests can fake the HTTP layer without sockets.
_urlopen = urllib.request.urlopen


def check_lm_studio(
    *, base_url: str = LM_STUDIO_BASE_URL, timeout: float = _LM_CHECK_TIMEOUT_SECONDS
) -> dict[str, Any]:
    """Preflight the LM Studio server; never raises.

    The chain runs to completion either way (rules-only classification,
    degraded synthesis) — this exists so the degradation is loud instead
    of silent.
    """
    try:
        payload = json.load(_urlopen(f"{base_url.rstrip('/')}/models", timeout=timeout))
        models = [entry.get("id", "?") for entry in payload.get("data", [])]
        return {"available": True, "base_url": base_url, "reason": None, "models": models}
    except Exception as exc:
        return {
            "available": False,
            "base_url": base_url,
            "reason": str(exc) or exc.__class__.__name__,
            "models": [],
        }


@dataclass(frozen=True)
class StepResult:
    status: str
    detail: str = ""


@dataclass(frozen=True)
class StepSpec:
    name: str
    callable: Callable[["RunContext"], StepResult]


@dataclass(frozen=True)
class RunContext:
    mode: str
    vaults: list[Path]
    personal_vault: Path
    business_vault: Path
    state_dir: Path
    json_out: Path
    dry_run: bool
    current_step: str = ""


def _step_export(context: RunContext) -> StepResult:
    script = _GRANOLA_DIR / "export_granola.py"
    result = subprocess.run(
        [str(_SYSTEM_PY), str(script)],
        cwd=_GRANOLA_DIR,
        timeout=_EXPORT_TIMEOUT_SECONDS,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or f"exit {result.returncode}").strip()
        raise RuntimeError(detail)
    detail = (result.stdout or "").strip().splitlines()
    return StepResult("ok", detail[-1] if detail else "export complete")


def _step_classify(context: RunContext) -> StepResult:
    parts: list[str] = []
    for vault in context.vaults:
        summary = classify_vault(vault=vault, dry_run=context.dry_run)
        parts.append(
            f"{vault.name}: {summary.get('auto_classified', 0)} new / "
            f"{summary.get('needs_review', 0)} review"
        )
    return StepResult("ok", "; ".join(parts))


def _step_collect(context: RunContext) -> StepResult:
    parts: list[str] = []
    for vault in context.vaults:
        topics = load_topics(vault)
        changed = 0
        for topic in topics:
            cache = collect_topic(vault=vault, topic=topic, json_out=context.json_out)
            if _cache_hash_changed(vault=vault, topic=topic, cache=cache):
                changed += 1
        parts.append(f"{vault.name}: {len(topics)} topics, {changed} hash-changed")
    return StepResult("ok", "; ".join(parts))


def _step_synthesize(context: RunContext) -> StepResult:
    details: list[str] = []
    degraded: list[str] = []
    for vault in context.vaults:
        for topic in load_topics(vault):
            try:
                result = synthesize_topic(
                    vault=vault,
                    topic_slug=topic.slug,
                    json_out=context.json_out,
                    dry_run=context.dry_run,
                )
            except Exception as exc:
                if _is_transient(exc):
                    degraded.append(f"{vault.name}/{topic.slug}: {exc}")
                    continue
                raise
            details.append(_synthesis_detail(vault=vault, result=result))
    if degraded:
        return StepResult("degraded", "; ".join(degraded))
    return StepResult("ok", "; ".join(details))


def _step_backlink(context: RunContext) -> StepResult:
    parts: list[str] = []
    for vault in context.vaults:
        summary = reconcile_backlinks(
            vault=vault,
            topics=load_topics(vault),
            json_out=context.json_out,
            dry_run=context.dry_run,
        )
        parts.append(_backlink_detail(vault=vault, summary=summary))
    return StepResult("ok", "; ".join(parts))


def _step_propose(context: RunContext) -> StepResult:
    return StepResult("stub", "U6 pending")


def _step_gardener(context: RunContext) -> StepResult:
    run_state = _read_run_state(context.state_dir)
    preview_state = dict(run_state)
    preview_state["complete"] = True
    preview_steps = dict(run_state.get("steps", {}))
    preview_steps["gardener"] = {
        "status": "ok",
        "detail": "gardener report written",
        "attempts": 1,
    }
    preview_state["steps"] = preview_steps
    report = build_report(
        vaults=context.vaults,
        run_state=preview_state,
        json_out=context.json_out,
    )
    write_report(vault=context.personal_vault, report_md=report, dry_run=context.dry_run)
    return StepResult("ok", "gardener report written")


STEP_SPECS: tuple[StepSpec, ...] = (
    StepSpec("export", _step_export),
    StepSpec("classify", _step_classify),
    StepSpec("collect", _step_collect),
    StepSpec("synthesize", _step_synthesize),
    StepSpec("backlink", _step_backlink),
    StepSpec("propose", _step_propose),
    StepSpec("gardener", _step_gardener),
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("nightly", "panel"), default="nightly")
    parser.add_argument("--steps", help="Comma-separated step names for surgical reruns.")
    parser.add_argument("--vaults", choices=("both", "personal", "business"), default="both")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--personal-vault", type=Path, default=_vault_from_env("PERSONAL"))
    parser.add_argument("--business-vault", type=Path, default=_vault_from_env("BUSINESS"))
    parser.add_argument("--state-dir", type=Path, default=_DEFAULT_STATE_DIR)
    parser.add_argument("--json-out", type=Path, default=_DEFAULT_JSON_OUT)
    args = parser.parse_args(argv)

    context = RunContext(
        mode=args.mode,
        vaults=_selected_vaults(
            selection=args.vaults,
            personal=args.personal_vault,
            business=args.business_vault,
        ),
        personal_vault=args.personal_vault,
        business_vault=args.business_vault,
        state_dir=args.state_dir,
        json_out=args.json_out,
        dry_run=args.dry_run,
    )
    return run_chain(context=context, step_names=_parse_steps(args.steps))


def run_chain(*, context: RunContext, step_names: list[str] | None = None) -> int:
    context.state_dir.mkdir(parents=True, exist_ok=True)
    context.json_out.mkdir(parents=True, exist_ok=True)

    lock = _acquire_lock(context.state_dir)
    if lock is None:
        print("nightly_chain already running; exiting without work.")
        return 0

    lm_status = check_lm_studio()
    run_state = {
        "started_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "mode": context.mode,
        "complete": False,
        "lm_studio": lm_status,
        "steps": {},
    }
    _write_run_state(context.state_dir, run_state)
    if not lm_status["available"]:
        print(
            f"⚠ LM Studio not reachable at {lm_status['base_url']} — "
            f"classification will be rules-only and topic synthesis will be "
            f"degraded or skipped ({lm_status['reason']})"
        )

    try:
        for spec in _steps_for_run(mode=context.mode, requested=step_names):
            _run_step(context=context, spec=spec, run_state=run_state)
        run_state["complete"] = True
        _write_run_state(context.state_dir, run_state)
        _append_run_logs(context=context, run_state=run_state)
        return 0
    finally:
        _release_lock(lock)


def _run_step(*, context: RunContext, spec: StepSpec, run_state: dict[str, Any]) -> None:
    step_context = replace(context, current_step=spec.name)
    attempts = 0
    while True:
        attempts += 1
        try:
            result = spec.callable(step_context)
        except Exception as exc:
            error_type = "TRANSIENT" if _is_transient(exc) else "PERMANENT"
            if error_type == "TRANSIENT" and attempts == 1:
                continue
            run_state["steps"][spec.name] = {
                "status": "failed",
                "detail": str(exc),
                "attempts": attempts,
                "error_type": error_type,
            }
            _write_run_state(context.state_dir, run_state)
            return

        run_state["steps"][spec.name] = {
            "status": result.status,
            "detail": result.detail,
            "attempts": attempts,
        }
        _write_run_state(context.state_dir, run_state)
        return


def _steps_for_run(*, mode: str, requested: list[str] | None) -> list[StepSpec]:
    specs = list(STEP_SPECS)
    known = {spec.name for spec in specs}
    if requested is not None:
        unknown = [name for name in requested if name not in known]
        if unknown:
            raise ValueError(f"unknown step(s): {', '.join(unknown)}")
        return [spec for spec in specs if spec.name in requested]
    if mode == "panel":
        return [spec for spec in specs if spec.name in _PANEL_STEPS]
    return specs


def _parse_steps(value: str | None) -> list[str] | None:
    if value is None:
        return None
    return [part.strip() for part in value.split(",") if part.strip()]


def _vault_from_env(name: str) -> Path:
    env_name = f"OBSIDIAN_{name}_VAULT"
    value = os.environ.get(env_name)
    if value:
        return Path(value).expanduser()
    return Path.home() / "Documents" / "ObsidianVault" / name.title()


def _selected_vaults(*, selection: str, personal: Path, business: Path) -> list[Path]:
    if selection == "personal":
        return [personal]
    if selection == "business":
        return [business]
    return [personal, business]


def _is_transient(exc: Exception) -> bool:
    if isinstance(exc, (ConnectionError, TimeoutError, subprocess.TimeoutExpired)):
        return True
    text = str(exc).casefold()
    return any(needle in text for needle in _TRANSIENT_NEEDLES)


def _cache_hash_changed(*, vault: Path, topic: Topic, cache: Path) -> bool:
    try:
        cache_data = json.loads(cache.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    current = _read_topic_hash(topic.path)
    cache_hash = cache_data.get("source_set_hash")
    return isinstance(cache_hash, str) and cache_hash != current


def _read_topic_hash(path: Path) -> str | None:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return None
    _, frontmatter, _ = text.split("---", 2)
    for line in frontmatter.splitlines():
        if line.startswith("source_set_hash:"):
            return line.split(":", 1)[1].strip().strip('"')
    return None


def _synthesis_detail(*, vault: Path, result: SynthesisResult) -> str:
    return f"{vault.name}/{result.slug}: {result.status}"


def _backlink_detail(*, vault: Path, summary: BacklinkSummary) -> str:
    detail = f"{vault.name}: {summary.updated} updated, {summary.removed} stale removed"
    if summary.errors:
        detail += f", {len(summary.errors)} errors"
    return detail


def _read_run_state(state_dir: Path) -> dict[str, Any]:
    path = state_dir / "last_run.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _write_run_state(state_dir: Path, run_state: dict[str, Any]) -> None:
    state_dir.mkdir(parents=True, exist_ok=True)
    path = state_dir / "last_run.json"
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(run_state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def _append_run_logs(*, context: RunContext, run_state: dict[str, Any]) -> None:
    if context.dry_run:
        return
    statuses = ", ".join(
        f"{name}={data.get('status', 'n/a')}"
        for name, data in run_state.get("steps", {}).items()
        if isinstance(data, dict)
    )
    for vault in context.vaults:
        append_log(vault, f"nightly_chain {context.mode}: complete={run_state['complete']} {statuses}")


def _acquire_lock(state_dir: Path) -> tuple[int, Path] | None:
    path = state_dir / _LOCK_NAME
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        if _remove_stale_lock(path):
            return _acquire_lock(state_dir)
        return None
    os.write(fd, str(os.getpid()).encode("ascii"))
    return (fd, path)


def _remove_stale_lock(path: Path) -> bool:
    try:
        text = path.read_text(encoding="utf-8").strip()
        pid = int(text)
    except (OSError, ValueError):
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        path.unlink(missing_ok=True)
        return True
    except PermissionError:
        return False
    return False


def _release_lock(lock: tuple[int, Path]) -> None:
    fd, path = lock
    try:
        os.close(fd)
    finally:
        path.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
