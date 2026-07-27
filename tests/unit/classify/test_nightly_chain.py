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


def test_gardener_step_writes_home_in_both_vaults(
    nightly_chain, tmp_path: Path, vaults: tuple[Path, Path], monkeypatch
) -> None:
    personal, business = vaults
    (personal / "wiki" / "topics").mkdir(parents=True)
    (business / "wiki" / "topics").mkdir(parents=True)
    (personal / "wiki" / "gardener.md").write_text(
        "Health score: 70/100\n",
        encoding="utf-8",
    )
    (personal / "wiki" / "index.md").write_text("# Wiki\n", encoding="utf-8")
    (business / "wiki" / "index.md").write_text("# Wiki\n", encoding="utf-8")

    monkeypatch.setattr(nightly_chain, "check_lm_studio", lambda: {"available": True})
    monkeypatch.setattr(
        nightly_chain,
        "_step_export",
        lambda context: nightly_chain.StepResult("ok", "export ok"),
    )
    monkeypatch.setattr(
        nightly_chain,
        "_step_classify",
        lambda context: nightly_chain.StepResult("ok", "classify ok"),
    )
    monkeypatch.setattr(
        nightly_chain,
        "_step_collect",
        lambda context: nightly_chain.StepResult("ok", "collect ok"),
    )
    monkeypatch.setattr(
        nightly_chain,
        "_step_synthesize",
        lambda context: nightly_chain.StepResult("ok", "synthesize ok"),
    )
    monkeypatch.setattr(
        nightly_chain,
        "_step_backlink",
        lambda context: nightly_chain.StepResult("ok", "backlink ok"),
    )
    monkeypatch.setattr(
        nightly_chain,
        "_step_propose",
        lambda context: nightly_chain.StepResult("ok", "propose ok"),
    )
    monkeypatch.setattr(
        nightly_chain,
        "STEP_SPECS",
        (
            nightly_chain.StepSpec("export", nightly_chain._step_export),
            nightly_chain.StepSpec("classify", nightly_chain._step_classify),
            nightly_chain.StepSpec("collect", nightly_chain._step_collect),
            nightly_chain.StepSpec("synthesize", nightly_chain._step_synthesize),
            nightly_chain.StepSpec("backlink", nightly_chain._step_backlink),
            nightly_chain.StepSpec("propose", nightly_chain._step_propose),
            nightly_chain.StepSpec("gardener", nightly_chain._step_gardener),
        ),
    )

    assert _run_cli(nightly_chain, tmp_path, vaults, "--mode", "nightly") == 0

    personal_home = (personal / "Home.md").read_text(encoding="utf-8")
    business_home = (business / "Home.md").read_text(encoding="utf-8")
    assert "## Topics & synthesis" in personal_home
    assert "Health 70/100" in personal_home
    assert "## Topics & synthesis" in business_home
    assert "[Wiki index](wiki/index.md)" in business_home
    assert (
        _state(tmp_path / "state")["steps"]["gardener"]["detail"]
        == "gardener report + 2 home pages written"
    )


def test_panel_mode_leaves_home_files_untouched(
    nightly_chain, tmp_path: Path, vaults: tuple[Path, Path], monkeypatch
) -> None:
    personal, business = vaults
    personal_home = personal / "Home.md"
    personal_home.write_text("# Home\nKeep me.\n", encoding="utf-8")

    monkeypatch.setattr(nightly_chain, "check_lm_studio", lambda: {"available": True})
    monkeypatch.setattr(
        nightly_chain,
        "STEP_SPECS",
        (
            nightly_chain.StepSpec(
                "classify",
                lambda context: nightly_chain.StepResult("ok", ""),
            ),
            nightly_chain.StepSpec(
                "collect",
                lambda context: nightly_chain.StepResult("ok", ""),
            ),
            nightly_chain.StepSpec(
                "synthesize",
                lambda context: nightly_chain.StepResult("ok", ""),
            ),
            nightly_chain.StepSpec(
                "backlink",
                lambda context: nightly_chain.StepResult("ok", ""),
            ),
            nightly_chain.StepSpec("gardener", nightly_chain._step_gardener),
        ),
    )

    assert _run_cli(nightly_chain, tmp_path, vaults, "--mode", "panel") == 0

    assert personal_home.read_text(encoding="utf-8") == "# Home\nKeep me.\n"
    assert not (business / "Home.md").exists()
    assert "gardener" not in _state(tmp_path / "state")["steps"]


class TestLMStudioPreflight:
    def _stub_steps(self, nightly_chain, monkeypatch) -> None:
        def ok(context):
            return nightly_chain.StepResult(status="ok", detail="ok")

        monkeypatch.setattr(
            nightly_chain,
            "STEP_SPECS",
            (nightly_chain.StepSpec("classify", ok),),
        )

    def test_check_lm_studio_unreachable_reports_unavailable(self, nightly_chain) -> None:
        status = nightly_chain.check_lm_studio(
            base_url="http://127.0.0.1:59999/v1", timeout=0.2
        )

        assert status["available"] is False
        assert status["base_url"] == "http://127.0.0.1:59999/v1"
        assert status["reason"]
        assert status["models"] == []

    def test_check_lm_studio_reachable_reports_models(self, nightly_chain, monkeypatch) -> None:
        import io

        def fake_urlopen(url, timeout=0):
            assert url.endswith("/models")
            return io.BytesIO(b'{"data": [{"id": "google/gemma-4-e4b"}]}')

        monkeypatch.setattr(nightly_chain, "_urlopen", fake_urlopen)

        status = nightly_chain.check_lm_studio(timeout=0.2)

        assert status["available"] is True
        assert status["reason"] is None
        assert status["models"] == ["google/gemma-4-e4b"]

    def test_chain_warns_and_stamps_state_when_lm_unavailable(
        self, nightly_chain, tmp_path: Path, vaults: tuple[Path, Path], monkeypatch, capsys
    ) -> None:
        self._stub_steps(nightly_chain, monkeypatch)

        def refuse(url, timeout=0):
            raise ConnectionRefusedError("connection refused")

        monkeypatch.setattr(nightly_chain, "_urlopen", refuse)

        assert _run_cli(nightly_chain, tmp_path, vaults, "--mode", "nightly") == 0

        state = _state(tmp_path / "state")
        assert state["lm_studio"]["available"] is False
        out = capsys.readouterr().out
        assert "LM Studio not reachable" in out
        assert "rules-only" in out
        assert state["complete"] is True  # graceful degradation preserved

    def test_chain_silent_and_stamps_state_when_lm_available(
        self, nightly_chain, tmp_path: Path, vaults: tuple[Path, Path], monkeypatch, capsys
    ) -> None:
        import io

        self._stub_steps(nightly_chain, monkeypatch)
        monkeypatch.setattr(
            nightly_chain,
            "_urlopen",
            lambda url, timeout=0: io.BytesIO(b'{"data": [{"id": "google/gemma-4-e4b"}]}'),
        )

        assert _run_cli(nightly_chain, tmp_path, vaults, "--mode", "panel") == 0

        state = _state(tmp_path / "state")
        assert state["lm_studio"]["available"] is True
        assert "LM Studio not reachable" not in capsys.readouterr().out
