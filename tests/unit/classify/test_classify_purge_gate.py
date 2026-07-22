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
