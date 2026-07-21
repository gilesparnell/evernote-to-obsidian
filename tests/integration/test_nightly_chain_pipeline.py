from __future__ import annotations

from pathlib import Path
from shutil import copytree

import pytest
import yaml

from scripts.classify.synthesize_topic import TopicSynthesis


FIXTURE_VAULT = Path(__file__).resolve().parents[1] / "fixtures" / "chain"


class FakeClient:
    pass


def _frontmatter(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    return yaml.safe_load(text.split("---", 2)[1]) or {}


def test_offline_nightly_chain_pipeline_steps_one_to_four_and_gardener(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from scripts.classify import nightly_chain

    personal = tmp_path / "Personal"
    business = tmp_path / "Business"
    copytree(FIXTURE_VAULT, personal)
    (business / "wiki" / "topics").mkdir(parents=True)

    def fake_classify_vault(**kwargs):
        return {
            "auto_classified": 0,
            "needs_review": 0,
            "skipped_already_classified": 0,
            "skipped_missing": 0,
            "purged": 0,
        }

    def fake_generate_structured(**kwargs):
        return TopicSynthesis(
            summary="Julie finances and estate legal planning are present. (src: B1)",
            timeline="- The fixture mentions topic planning. (src: B1)",
            key_facts="- The note links money and probate planning. (src: B1)",
            contradictions="",
            open_questions="- What follow-up belongs on the topic? (src: B1)",
        )

    monkeypatch.setattr(nightly_chain, "classify_vault", fake_classify_vault)
    monkeypatch.setattr(
        "scripts.classify.synthesize_topic.generate_structured",
        fake_generate_structured,
    )

    exit_code = nightly_chain.main(
        [
            "--mode",
            "nightly",
            "--steps",
            "classify,collect,synthesize,backlink,gardener",
            "--vaults",
            "both",
            "--personal-vault",
            str(personal),
            "--business-vault",
            str(business),
            "--state-dir",
            str(tmp_path / "state"),
            "--json-out",
            str(tmp_path / "cache"),
        ]
    )

    assert exit_code == 0
    topic_page = personal / "wiki" / "topics" / "julie-finances.md"
    page_text = topic_page.read_text(encoding="utf-8")
    assert "source_set_hash: sha256:" in page_text
    assert "## Summary" in page_text
    assert "## Source blocks" in page_text

    assert _frontmatter(personal / "Julie finances title match.md")["topics"] == [
        "[[julie-finances]]"
    ]
    assert "topics" not in _frontmatter(personal / "Stale managed entry.md")

    gardener = personal / "wiki" / "gardener.md"
    gardener_text = gardener.read_text(encoding="utf-8")
    assert "| classify | ok | Personal:" in gardener_text
    assert "| collect | ok | Personal:" in gardener_text
    assert "| synthesize |" in gardener_text
    assert "| backlink | ok | Personal:" in gardener_text
    assert "| gardener | ok |" in gardener_text
