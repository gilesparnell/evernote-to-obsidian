"""Purge gate must be disableable for unattended (chain) runs.

Locked invariant (U3 spec): the nightly chain never deletes notes
unattended. Purge remains available for operator-run batches only.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture()
def vault(tmp_path: Path) -> Path:
    v = tmp_path / "Vault"
    v.mkdir()
    (v / "Tiny junk note.md").write_text("x\n", encoding="utf-8")
    return v


def _classify(vault: Path, **kwargs):
    from scripts.classify.classify_vault import classify_vault

    return classify_vault(vault=vault, **kwargs)


def test_purge_disabled_keeps_file_and_queues_for_review(vault: Path) -> None:
    summary = _classify(vault, purge_enabled=False)

    assert (vault / "Tiny junk note.md").exists()
    assert summary["purged"] == 0
    assert summary["needs_review"] == 1
    assert "Tiny junk note" in summary["review_queue_md"]
    assert "purge-candidate" in summary["review_queue_md"]


def test_purge_enabled_default_still_deletes_with_manifest(vault: Path) -> None:
    summary = _classify(vault)

    assert not (vault / "Tiny junk note.md").exists()
    assert summary["purged"] == 1
    manifest = json.loads(
        (vault / ".classify_deleted_manifest.json").read_text(encoding="utf-8")
    )
    assert any("Tiny junk note.md" in e["path"] for e in manifest["deleted"])


def test_chain_classify_step_disables_purge(tmp_path: Path, monkeypatch) -> None:
    from scripts.classify import nightly_chain

    captured: list[dict] = []

    def fake_classify_vault(**kwargs):
        captured.append(kwargs)
        return {"auto": 0, "review": 0, "purged": 0}

    monkeypatch.setattr(nightly_chain, "classify_vault", fake_classify_vault)

    personal = tmp_path / "Personal"
    business = tmp_path / "Business"
    (personal / "wiki").mkdir(parents=True)
    (business / "wiki").mkdir(parents=True)
    nightly_chain.main(
        [
            "--mode",
            "panel",
            "--steps",
            "classify",
            "--state-dir",
            str(tmp_path / "state"),
            "--json-out",
            str(tmp_path / "cache"),
            "--personal-vault",
            str(personal),
            "--business-vault",
            str(business),
        ]
    )

    assert captured, "chain never called classify_vault"
    assert all(kw.get("purge_enabled") is False for kw in captured)


def _run_classify_step(tmp_path: Path, monkeypatch, extra_args: list[str] | None = None):
    """Drive the chain's classify step with classify_vault stubbed out,
    returning the kwargs it was called with.
    """
    from scripts.classify import nightly_chain

    captured: list[dict] = []

    def fake_classify_vault(**kwargs):
        captured.append(kwargs)
        return {"auto": 0, "review": 0, "purged": 0}

    monkeypatch.setattr(nightly_chain, "classify_vault", fake_classify_vault)

    personal = tmp_path / "Personal"
    business = tmp_path / "Business"
    (personal / "wiki").mkdir(parents=True)
    (business / "wiki").mkdir(parents=True)
    nightly_chain.main(
        [
            "--mode", "panel",
            "--steps", "classify",
            "--state-dir", str(tmp_path / "state"),
            "--json-out", str(tmp_path / "cache"),
            "--personal-vault", str(personal),
            "--business-vault", str(business),
            *(extra_args or []),
        ]
    )
    return captured


class TestNightlyClassifyCap:
    """The chain must cap how many notes one run will classify.

    Uncapped, a batch of newly re-opened notes (or any bulk import) becomes a
    single multi-hour run holding the LM resident — a larger local model can
    push past a minute per note, making 70 notes an hour-plus job and a full
    corpus re-open a day. Capping drains a backlog over successive nights.
    """

    def test_classify_step_passes_a_limit(self, tmp_path: Path, monkeypatch) -> None:
        captured = _run_classify_step(tmp_path, monkeypatch)
        assert captured, "chain never called classify_vault"
        assert all(
            kw.get("limit") == nightly_classify_limit() for kw in captured
        )

    def test_limit_is_a_positive_integer(self) -> None:
        assert isinstance(nightly_classify_limit(), int)
        assert nightly_classify_limit() > 0

    def test_backlog_flag_lifts_the_cap(self, tmp_path: Path, monkeypatch) -> None:
        """`--backlog` is the deliberate 'drain everything' escape hatch."""
        captured = _run_classify_step(tmp_path, monkeypatch, ["--backlog"])
        assert captured, "chain never called classify_vault"
        assert all(kw.get("limit") is None for kw in captured)


def nightly_classify_limit() -> int:
    from scripts.classify.nightly_chain import NIGHTLY_CLASSIFY_LIMIT

    return NIGHTLY_CLASSIFY_LIMIT
