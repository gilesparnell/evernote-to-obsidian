from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture()
def nightly_chain():
    from scripts.classify import nightly_chain

    return nightly_chain


@pytest.fixture()
def vaults(tmp_path: Path) -> tuple[Path, Path]:
    personal = tmp_path / "Personal"
    business = tmp_path / "Business"
    (personal / "wiki").mkdir(parents=True)
    (business / "wiki").mkdir(parents=True)
    return personal, business


def _state(state_dir: Path) -> dict:
    return json.loads((state_dir / "last_run.json").read_text(encoding="utf-8"))


def _run_cli(nightly_chain, tmp_path: Path, vaults: tuple[Path, Path], *args: str) -> int:
    personal, business = vaults
    return nightly_chain.main(
        [
            "--state-dir",
            str(tmp_path / "state"),
            "--json-out",
            str(tmp_path / "cache"),
            "--personal-vault",
            str(personal),
            "--business-vault",
            str(business),
            *args,
        ]
    )


def test_nightly_mode_runs_steps_zero_to_six_in_order(
    nightly_chain, tmp_path: Path, vaults: tuple[Path, Path], monkeypatch
) -> None:
    calls: list[str] = []

    def step(name: str):
        def run(context):
            calls.append(name)
            return nightly_chain.StepResult(status="ok", detail=f"{name} ok")

        return run

    monkeypatch.setattr(
        nightly_chain,
        "STEP_SPECS",
        tuple(
            nightly_chain.StepSpec(name, step(name))
            for name in [
                "export",
                "classify",
                "collect",
                "synthesize",
                "backlink",
                "propose",
                "gardener",
            ]
        ),
    )

    assert _run_cli(nightly_chain, tmp_path, vaults, "--mode", "nightly") == 0

    assert calls == [
        "export",
        "classify",
        "collect",
        "synthesize",
        "backlink",
        "propose",
        "gardener",
    ]
    run_state = _state(tmp_path / "state")
    assert run_state["complete"] is True
    assert list(run_state["steps"]) == calls


def test_panel_mode_runs_classify_collect_synthesize_backlink_only(
    nightly_chain, tmp_path: Path, vaults: tuple[Path, Path], monkeypatch
) -> None:
    calls: list[str] = []

    def run(context):
        calls.append(context.current_step)
        return nightly_chain.StepResult(status="ok", detail="")

    monkeypatch.setattr(
        nightly_chain,
        "STEP_SPECS",
        tuple(
            nightly_chain.StepSpec(name, run)
            for name in [
                "export",
                "classify",
                "collect",
                "synthesize",
                "backlink",
                "propose",
                "gardener",
            ]
        ),
    )

    assert _run_cli(nightly_chain, tmp_path, vaults, "--mode", "panel") == 0

    assert calls == ["classify", "collect", "synthesize", "backlink"]
    assert list(_state(tmp_path / "state")["steps"]) == calls


def test_steps_override_runs_exact_comma_list(
    nightly_chain, tmp_path: Path, vaults: tuple[Path, Path], monkeypatch
) -> None:
    calls: list[str] = []

    def run(context):
        calls.append(context.current_step)
        return nightly_chain.StepResult(status="ok", detail="")

    monkeypatch.setattr(
        nightly_chain,
        "STEP_SPECS",
        tuple(nightly_chain.StepSpec(name, run) for name in ["export", "classify", "gardener"]),
    )

    assert (
        _run_cli(
            nightly_chain,
            tmp_path,
            vaults,
            "--mode",
            "nightly",
            "--steps",
            "classify,gardener",
        )
        == 0
    )

    assert calls == ["classify", "gardener"]


def test_failure_marks_step_and_independent_later_steps_continue(
    nightly_chain, tmp_path: Path, vaults: tuple[Path, Path], monkeypatch
) -> None:
    calls: list[str] = []

    def fail(context):
        calls.append(context.current_step)
        raise ValueError("bad frontmatter")

    def ok(context):
        calls.append(context.current_step)
        return nightly_chain.StepResult(status="ok", detail="continued")

    monkeypatch.setattr(
        nightly_chain,
        "STEP_SPECS",
        (
            nightly_chain.StepSpec("classify", fail),
            nightly_chain.StepSpec("collect", ok),
            nightly_chain.StepSpec("backlink", ok),
            nightly_chain.StepSpec("gardener", ok),
        ),
    )

    assert _run_cli(nightly_chain, tmp_path, vaults, "--mode", "nightly") == 0

    assert calls == ["classify", "collect", "backlink", "gardener"]
    run_state = _state(tmp_path / "state")
    assert run_state["steps"]["classify"]["status"] == "failed"
    assert "bad frontmatter" in run_state["steps"]["classify"]["detail"]
    assert run_state["steps"]["gardener"]["status"] == "ok"
    assert run_state["complete"] is True


def test_transient_error_retries_once_then_records_failure(
    nightly_chain, tmp_path: Path, vaults: tuple[Path, Path], monkeypatch
) -> None:
    attempts = 0

    def transient(context):
        nonlocal attempts
        attempts += 1
        raise TimeoutError("LM timeout")

    monkeypatch.setattr(
        nightly_chain,
        "STEP_SPECS",
        (nightly_chain.StepSpec("synthesize", transient),),
    )

    assert _run_cli(nightly_chain, tmp_path, vaults, "--mode", "nightly") == 0

    assert attempts == 2
    step = _state(tmp_path / "state")["steps"]["synthesize"]
    assert step["status"] == "failed"
    assert step["attempts"] == 2
    assert step["error_type"] == "TRANSIENT"


def test_lock_excludes_second_run_without_error(
    nightly_chain, tmp_path: Path, vaults: tuple[Path, Path], monkeypatch, capsys
) -> None:
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    (state_dir / "nightly_chain.lock").write_text("already running\n", encoding="utf-8")

    called = False

    def run(context):
        nonlocal called
        called = True
        return nightly_chain.StepResult(status="ok", detail="")

    monkeypatch.setattr(
        nightly_chain,
        "STEP_SPECS",
        (nightly_chain.StepSpec("classify", run),),
    )

    assert _run_cli(nightly_chain, tmp_path, vaults, "--mode", "nightly") == 0

    assert called is False
    assert "already running" in capsys.readouterr().out


def test_dry_run_propagates_to_every_step(
    nightly_chain, tmp_path: Path, vaults: tuple[Path, Path], monkeypatch
) -> None:
    seen: list[bool] = []

    def run(context):
        seen.append(context.dry_run)
        return nightly_chain.StepResult(status="ok", detail="")

    monkeypatch.setattr(
        nightly_chain,
        "STEP_SPECS",
        (nightly_chain.StepSpec("classify", run), nightly_chain.StepSpec("collect", run)),
    )

    assert _run_cli(nightly_chain, tmp_path, vaults, "--mode", "nightly", "--dry-run") == 0

    assert seen == [True, True]


def test_complete_flips_only_after_final_step(
    nightly_chain, tmp_path: Path, vaults: tuple[Path, Path], monkeypatch
) -> None:
    observed: list[bool] = []

    def observe(context):
        state_path = context.state_dir / "last_run.json"
        observed.append(json.loads(state_path.read_text(encoding="utf-8"))["complete"])
        return nightly_chain.StepResult(status="ok", detail="")

    monkeypatch.setattr(
        nightly_chain,
        "STEP_SPECS",
        (nightly_chain.StepSpec("classify", observe),),
    )

    assert _run_cli(nightly_chain, tmp_path, vaults, "--mode", "nightly") == 0

    assert observed == [False]
    assert _state(tmp_path / "state")["complete"] is True


def test_gardener_runs_even_when_every_other_step_failed(
    nightly_chain, tmp_path: Path, vaults: tuple[Path, Path], monkeypatch
) -> None:
    calls: list[str] = []

    def fail(context):
        calls.append(context.current_step)
        raise RuntimeError("boom")

    def gardener(context):
        calls.append(context.current_step)
        return nightly_chain.StepResult(status="ok", detail="report written")

    monkeypatch.setattr(
        nightly_chain,
        "STEP_SPECS",
        (
            nightly_chain.StepSpec("classify", fail),
            nightly_chain.StepSpec("collect", fail),
            nightly_chain.StepSpec("synthesize", fail),
            nightly_chain.StepSpec("backlink", fail),
            nightly_chain.StepSpec("gardener", gardener),
        ),
    )

    assert _run_cli(nightly_chain, tmp_path, vaults, "--mode", "nightly") == 0

    assert calls == ["classify", "collect", "synthesize", "backlink", "gardener"]
    assert _state(tmp_path / "state")["steps"]["gardener"]["status"] == "ok"
