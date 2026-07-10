from __future__ import annotations

from pathlib import Path
from shutil import copytree

import pytest

from scripts.classify.collect_topic import collect_topic
from scripts.classify.synthesize_topic import TopicSynthesis, synthesize_topic
from scripts.classify.topics import load_topics


FIXTURE_VAULT = Path(__file__).resolve().parents[1] / "fixtures" / "synthesis"


class FakeClient:
    pass


def test_offline_collector_to_synthesis_pipeline(tmp_path: Path, monkeypatch) -> None:
    vault = tmp_path / "synthesis"
    copytree(FIXTURE_VAULT, vault)
    cache_dir = tmp_path / "cache"
    topic = next(topic for topic in load_topics(vault) if topic.slug == "julies-finances")
    collect_topic(vault=vault, topic=topic, json_out=cache_dir)

    def fake_generate_structured(**kwargs):
        return TopicSynthesis(
            summary="Julie finances are present in the fixture notes. (src: B1)",
            timeline="- The archive mentions Julie's money. (src: B2)",
            key_facts="- Kenton financials are part of the topic. (src: B1)",
            contradictions="",
            open_questions="- What follow-up is needed? (src: B1)",
        )

    monkeypatch.setattr(
        "scripts.classify.synthesize_topic.generate_structured",
        fake_generate_structured,
    )

    result = synthesize_topic(
        vault=vault,
        topic_slug="julies-finances",
        client=FakeClient(),
        json_out=cache_dir,
    )

    assert result.status == "wrote"
    page = (vault / "wiki" / "topics" / "julies-finances.md").read_text(
        encoding="utf-8"
    )
    assert "source_set_hash: sha256:" in page
    assert "sources:" in page
    assert "<!-- @generated:start -->" in page
    assert "<!-- @generated:end -->" in page
    assert "<!-- @user:start -->" in page
    assert "<!-- @user:end -->" in page
    assert "## Summary" in page
    assert "## Timeline" in page
    assert "## Key facts" in page
    assert "## Open questions" in page
    assert "## Source blocks" in page
    assert "- B1" in page


@pytest.mark.integration_live
def test_live_lmstudio_synthesis_pipeline(tmp_path: Path) -> None:
    vault = tmp_path / "synthesis"
    copytree(FIXTURE_VAULT, vault)
    cache_dir = tmp_path / "cache"
    topic = next(topic for topic in load_topics(vault) if topic.slug == "julies-finances")
    collect_topic(vault=vault, topic=topic, json_out=cache_dir)

    result = synthesize_topic(
        vault=vault,
        topic_slug="julies-finances",
        json_out=cache_dir,
    )

    assert result.status == "wrote"
    page = (vault / "wiki" / "topics" / "julies-finances.md").read_text(
        encoding="utf-8"
    )
    assert "## Source blocks" in page
    assert "(src: B" in page
