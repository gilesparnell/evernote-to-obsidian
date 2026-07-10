from __future__ import annotations

import json
import os
from pathlib import Path
from shutil import copytree

import pytest
import yaml

from scripts.classify import synthesize_topic
from scripts.classify.synthesize_topic import TopicSynthesis


def _write_topic(vault: Path, *, body: str = "# Julie finances\n") -> Path:
    topic = vault / "wiki" / "topics" / "julies-finances.md"
    topic.parent.mkdir(parents=True, exist_ok=True)
    topic.write_text(
        "---\n"
        "type: topic\n"
        "slug: julies-finances\n"
        "aliases: [Julie finances, Julie's money]\n"
        "status: active\n"
        "---\n\n"
        f"{body}",
        encoding="utf-8",
    )
    return topic


def _write_source(vault: Path, rel: str, text: str, *, title: str | None = None) -> None:
    path = vault / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    title_line = f'title: "{title or path.stem}"\n'
    path.write_text(f"---\n{title_line}---\n\n{text}\n", encoding="utf-8")


def _write_cache(
    cache_dir: Path,
    vault: Path,
    *,
    source_set_hash: str = "sha256:abc",
    sources: list[dict] | None = None,
) -> Path:
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache = cache_dir / f"{vault.name}-julies-finances.json"
    cache.write_text(
        json.dumps(
            {
                "slug": "julies-finances",
                "vault": str(vault),
                "generated_at": "2026-07-09T21:00:00+10:00",
                "source_set_hash": source_set_hash,
                "sources": sources
                if sources is not None
                else [
                    {
                        "path": "source-one.md",
                        "title": "Source One",
                        "mtime": "2026-07-09",
                        "matched_aliases": ["Julie finances"],
                        "quotes": ["Julie finances has one sourced quote."],
                    }
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return cache


def _patch_model(monkeypatch: pytest.MonkeyPatch, result: TopicSynthesis) -> dict[str, int]:
    calls = {"count": 0}

    def fake_generate_structured(**kwargs):
        calls["count"] += 1
        assert kwargs["client"] is FAKE_CLIENT
        assert kwargs["output_model"] is TopicSynthesis
        return result

    monkeypatch.setattr(synthesize_topic, "generate_structured", fake_generate_structured)
    return calls


def _default_result(**overrides: str) -> TopicSynthesis:
    data = {
        "summary": "Julie finances are documented in the archive. (src: B1)",
        "timeline": "- Reviewed in July. (src: B1)",
        "key_facts": "- Kenton financials are mentioned. (src: B1)",
        "contradictions": "",
        "open_questions": "- What changed next? (src: B1)",
    }
    data.update(overrides)
    return TopicSynthesis(**data)


def _frontmatter(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    return yaml.safe_load(text.split("---", 2)[1])


def _generated_body(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    return text.split("<!-- @generated:start -->", 1)[1].split(
        "<!-- @generated:end -->", 1
    )[0]


def _snapshot_tree(root: Path) -> dict[str, bytes]:
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


class FAKE_CLIENT:
    pass


def test_idempotence_skip_does_not_call_model_or_write(tmp_path: Path, monkeypatch) -> None:
    vault = tmp_path / "vault"
    topic = _write_topic(vault)
    topic.write_text(
        topic.read_text(encoding="utf-8").replace(
            "status: active\n",
            "status: active\nsource_set_hash: sha256:abc\n",
        ),
        encoding="utf-8",
    )
    cache_dir = tmp_path / "cache"
    _write_cache(cache_dir, vault, source_set_hash="sha256:abc")
    before = _snapshot_tree(vault)
    calls = _patch_model(monkeypatch, _default_result())

    result = synthesize_topic.synthesize_topic(
        vault=vault,
        topic_slug="julies-finances",
        client=FAKE_CLIENT,
        json_out=cache_dir,
    )

    assert result.status == "skipped-unchanged"
    assert calls["count"] == 0
    assert _snapshot_tree(vault) == before


def test_force_regenerates_when_hash_matches(tmp_path: Path, monkeypatch) -> None:
    vault = tmp_path / "vault"
    topic = _write_topic(vault)
    topic.write_text(
        topic.read_text(encoding="utf-8").replace(
            "status: active\n",
            "status: active\nsource_set_hash: sha256:abc\n",
        ),
        encoding="utf-8",
    )
    cache_dir = tmp_path / "cache"
    _write_source(vault, "source-one.md", "Julie finances has one sourced quote.")
    _write_cache(cache_dir, vault, source_set_hash="sha256:abc")
    calls = _patch_model(monkeypatch, _default_result())

    result = synthesize_topic.synthesize_topic(
        vault=vault,
        topic_slug="julies-finances",
        client=FAKE_CLIENT,
        json_out=cache_dir,
        force=True,
    )

    assert result.status == "wrote"
    assert calls["count"] == 1
    assert "## Source blocks" in topic.read_text(encoding="utf-8")


def test_degraded_budget_sets_frontmatter_flag(tmp_path: Path, monkeypatch) -> None:
    vault = tmp_path / "vault"
    topic = _write_topic(vault)
    cache_dir = tmp_path / "cache"
    _write_source(vault, "source-one.md", "Julie finances " + ("long text " * 200))
    _write_cache(cache_dir, vault)
    _patch_model(monkeypatch, _default_result())
    monkeypatch.setenv("LMSTUDIO_CTX", "80")

    synthesize_topic.synthesize_topic(
        vault=vault,
        topic_slug="julies-finances",
        client=FAKE_CLIENT,
        json_out=cache_dir,
    )

    assert _frontmatter(topic)["prompt_degraded"] is True


def test_inference_segregation_and_out_of_range_demotions(tmp_path: Path, monkeypatch) -> None:
    vault = tmp_path / "vault"
    topic = _write_topic(vault)
    cache_dir = tmp_path / "cache"
    _write_source(vault, "source-one.md", "Julie finances has one sourced quote.")
    _write_cache(cache_dir, vault)
    _patch_model(
        monkeypatch,
        _default_result(
            summary=(
                "Kept sourced sentence. (src: B1) "
                "Demoted invented citation. (src: B9) "
                "Demoted unsupported sentence."
            )
        ),
    )

    synthesize_topic.synthesize_topic(
        vault=vault,
        topic_slug="julies-finances",
        client=FAKE_CLIENT,
        json_out=cache_dir,
    )

    body = _generated_body(topic)
    summary = body.split("## Timeline", 1)[0]
    inferences = body.split("## Inferences (not in the source)", 1)[1]
    assert "Kept sourced sentence. (src: B1)" in summary
    assert "Demoted invented citation. (src: B9)" not in summary
    assert "Demoted invented citation. (src: B9)" in inferences
    assert "Demoted unsupported sentence." in inferences


def test_multi_source_citation_is_kept_not_demoted(tmp_path: Path, monkeypatch) -> None:
    """A claim citing several in-range sources '(src: B1, B2)' must stay in the

    factual section. The live T7 run showed every multi-source claim being
    wrongly demoted to Inferences, emptying Summary/Key facts/Open questions.
    """
    vault = tmp_path / "vault"
    topic = _write_topic(vault)
    cache_dir = tmp_path / "cache"
    two_sources = [
        {"path": "source-one.md", "title": "Source One", "mtime": "2026-07-09",
         "matched_aliases": ["Julie finances"], "quotes": ["q1"]},
        {"path": "source-two.md", "title": "Source Two", "mtime": "2026-07-08",
         "matched_aliases": ["Julie finances"], "quotes": ["q2"]},
    ]
    _write_source(vault, "source-one.md", "Julie finances one.")
    _write_source(vault, "source-two.md", "Julie finances two.")
    _write_cache(cache_dir, vault, sources=two_sources)
    _patch_model(
        monkeypatch,
        _default_result(summary="Both sources agree on the grant. (src: B1, B2)"),
    )

    synthesize_topic.synthesize_topic(
        vault=vault, topic_slug="julies-finances", client=FAKE_CLIENT, json_out=cache_dir
    )

    body = _generated_body(topic)
    summary = body.split("## Timeline", 1)[0]
    assert "Both sources agree on the grant. (src: B1, B2)" in summary


def test_multi_source_citation_with_one_out_of_range_is_demoted(
    tmp_path: Path, monkeypatch
) -> None:
    """If ANY cited source in a multi-cite is out of range, the claim is still

    demoted — an invented block number taints the whole claim.
    """
    vault = tmp_path / "vault"
    topic = _write_topic(vault)
    cache_dir = tmp_path / "cache"
    _write_source(vault, "source-one.md", "Julie finances one.")
    _write_cache(cache_dir, vault)  # single source → B2 is out of range
    _patch_model(
        monkeypatch,
        _default_result(summary="Mixed valid and invented. (src: B1, B2)"),
    )

    synthesize_topic.synthesize_topic(
        vault=vault, topic_slug="julies-finances", client=FAKE_CLIENT, json_out=cache_dir
    )

    body = _generated_body(topic)
    inferences = body.split("## Inferences (not in the source)", 1)[1]
    assert "Mixed valid and invented. (src: B1, B2)" in inferences


def test_contradiction_callout_prefixes_every_line_and_has_no_blank_gap(
    tmp_path: Path, monkeypatch
) -> None:
    """Every line of a multi-line contradiction must be '>'-prefixed with no

    blank line after the marker, or Obsidian breaks out of the callout box.
    """
    vault = tmp_path / "vault"
    topic = _write_topic(vault)
    cache_dir = tmp_path / "cache"
    _write_source(vault, "source-one.md", "Julie finances one.")
    _write_cache(cache_dir, vault)
    _patch_model(
        monkeypatch,
        _default_result(
            contradictions="First conflicting line. (src: B1)\nSecond conflicting line. (src: B1)"
        ),
    )

    synthesize_topic.synthesize_topic(
        vault=vault, topic_slug="julies-finances", client=FAKE_CLIENT, json_out=cache_dir
    )

    body = _generated_body(topic)
    callout = body.split("> [!contradiction]", 1)[1].split("## Open questions", 1)[0]
    # no blank line immediately after the marker
    assert not callout.startswith("\n\n")
    # every non-empty content line is quote-prefixed
    for line in callout.splitlines():
        if line.strip():
            assert line.startswith(">"), f"callout line not prefixed: {line!r}"


def test_unknown_wikilinks_are_stripped_but_known_links_remain(
    tmp_path: Path, monkeypatch
) -> None:
    vault = tmp_path / "vault"
    topic = _write_topic(vault)
    (vault / "wiki" / "Known Page.md").write_text("known\n", encoding="utf-8")
    cache_dir = tmp_path / "cache"
    _write_source(vault, "source-one.md", "Julie finances has one sourced quote.")
    _write_cache(cache_dir, vault)
    _patch_model(
        monkeypatch,
        _default_result(summary="[[Known Page]] stays and [[Unknown Page]] goes. (src: B1)"),
    )

    synthesize_topic.synthesize_topic(
        vault=vault,
        topic_slug="julies-finances",
        client=FAKE_CLIENT,
        json_out=cache_dir,
    )

    body = _generated_body(topic)
    assert "[[Known Page]]" in body
    assert "[[Unknown Page]]" not in body
    assert "Unknown Page goes" in body


def test_sentinel_user_region_and_aliases_are_preserved(tmp_path: Path, monkeypatch) -> None:
    vault = tmp_path / "vault"
    topic = _write_topic(
        vault,
        body=(
            "<!-- @generated:start -->\nold\n<!-- @generated:end -->\n\n"
            "<!-- @user:start -->\nhand written note\n<!-- @user:end -->\n"
        ),
    )
    cache_dir = tmp_path / "cache"
    _write_source(vault, "source-one.md", "Julie finances has one sourced quote.")
    _write_cache(cache_dir, vault)
    _patch_model(monkeypatch, _default_result())

    synthesize_topic.synthesize_topic(
        vault=vault,
        topic_slug="julies-finances",
        client=FAKE_CLIENT,
        json_out=cache_dir,
    )

    text = topic.read_text(encoding="utf-8")
    assert "<!-- @user:start -->\nhand written note\n<!-- @user:end -->" in text
    assert _frontmatter(topic)["aliases"] == ["Julie finances", "Julie's money"]


def test_malformed_sentinels_raise_and_never_write(tmp_path: Path, monkeypatch) -> None:
    vault = tmp_path / "vault"
    topic = _write_topic(vault, body="<!-- @generated:start -->\nunterminated\n")
    cache_dir = tmp_path / "cache"
    _write_source(vault, "source-one.md", "Julie finances has one sourced quote.")
    _write_cache(cache_dir, vault)
    before = topic.read_bytes()
    _patch_model(monkeypatch, _default_result())

    with pytest.raises(ValueError):
        synthesize_topic.synthesize_topic(
            vault=vault,
            topic_slug="julies-finances",
            client=FAKE_CLIENT,
            json_out=cache_dir,
        )

    assert topic.read_bytes() == before


def test_zero_source_refuses_model_and_leaves_page_untouched(
    tmp_path: Path, monkeypatch
) -> None:
    vault = tmp_path / "vault"
    topic = _write_topic(vault)
    cache_dir = tmp_path / "cache"
    _write_cache(cache_dir, vault, sources=[])
    before_page = topic.read_bytes()
    calls = _patch_model(monkeypatch, _default_result())

    result = synthesize_topic.synthesize_topic(
        vault=vault,
        topic_slug="julies-finances",
        client=FAKE_CLIENT,
        json_out=cache_dir,
    )

    assert result.status == "skipped-zero-sources"
    assert calls["count"] == 0
    assert topic.read_bytes() == before_page
    assert "zero sources" in (vault / "wiki" / "log.md").read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("contradictions", "expected"),
    [
        ("", False),
        ("One note disagrees with another. (src: B1)", True),
    ],
)
def test_contradiction_callout_present_iff_non_empty(
    tmp_path: Path, monkeypatch, contradictions: str, expected: bool
) -> None:
    vault = tmp_path / "vault"
    topic = _write_topic(vault)
    cache_dir = tmp_path / "cache"
    _write_source(vault, "source-one.md", "Julie finances has one sourced quote.")
    _write_cache(cache_dir, vault)
    _patch_model(monkeypatch, _default_result(contradictions=contradictions))

    synthesize_topic.synthesize_topic(
        vault=vault,
        topic_slug="julies-finances",
        client=FAKE_CLIENT,
        json_out=cache_dir,
    )

    assert ("> [!contradiction]" in _generated_body(topic)) is expected


def test_confidence_formula_bounds() -> None:
    assert synthesize_topic.compute_confidence(source_count=0, quality=0) == 0
    assert synthesize_topic.compute_confidence(source_count=3, quality=1) == 1
    assert synthesize_topic.compute_confidence(source_count=6, quality=2) == 1
    assert synthesize_topic.compute_confidence(source_count=1, quality=-1) == pytest.approx(
        1 / 6
    )


def test_dry_run_writes_nothing_including_cache_log_and_index(
    tmp_path: Path, monkeypatch
) -> None:
    vault = tmp_path / "vault"
    _write_topic(vault)
    _write_source(vault, "source-one.md", "Julie finances has one sourced quote.")
    cache_dir = tmp_path / "cache"
    _write_cache(cache_dir, vault)
    before_vault = _snapshot_tree(vault)
    before_cache = _snapshot_tree(cache_dir)
    _patch_model(monkeypatch, _default_result())

    result = synthesize_topic.synthesize_topic(
        vault=vault,
        topic_slug="julies-finances",
        client=FAKE_CLIENT,
        json_out=cache_dir,
        dry_run=True,
    )

    assert result.status == "dry-run"
    assert _snapshot_tree(vault) == before_vault
    assert _snapshot_tree(cache_dir) == before_cache


def test_dry_run_with_missing_cache_uses_temp_cache_only(
    tmp_path: Path, monkeypatch
) -> None:
    vault = tmp_path / "vault"
    _write_topic(vault)
    _write_source(vault, "source-one.md", "Julie finances has one sourced quote.")
    cache_dir = tmp_path / "cache"
    before_vault = _snapshot_tree(vault)
    _patch_model(monkeypatch, _default_result())

    result = synthesize_topic.synthesize_topic(
        vault=vault,
        topic_slug="julies-finances",
        client=FAKE_CLIENT,
        json_out=cache_dir,
        dry_run=True,
    )

    assert result.status == "dry-run"
    assert _snapshot_tree(vault) == before_vault
    assert not cache_dir.exists()


def test_missing_cache_auto_runs_collector(tmp_path: Path, monkeypatch) -> None:
    vault = tmp_path / "vault"
    topic = _write_topic(vault)
    _write_source(vault, "source-one.md", "Julie finances has one sourced quote.")
    cache_dir = tmp_path / "cache"
    _patch_model(monkeypatch, _default_result())

    result = synthesize_topic.synthesize_topic(
        vault=vault,
        topic_slug="julies-finances",
        client=FAKE_CLIENT,
        json_out=cache_dir,
    )

    assert result.status == "wrote"
    assert (cache_dir / f"{vault.name}-julies-finances.json").exists()
    assert "## Source blocks" in topic.read_text(encoding="utf-8")


def test_real_write_updates_log_and_index(tmp_path: Path, monkeypatch) -> None:
    vault = tmp_path / "vault"
    _write_topic(vault)
    _write_source(vault, "source-one.md", "Julie finances has one sourced quote.")
    cache_dir = tmp_path / "cache"
    _write_cache(cache_dir, vault)
    _patch_model(monkeypatch, _default_result(summary="Index summary line. (src: B1)"))

    synthesize_topic.synthesize_topic(
        vault=vault,
        topic_slug="julies-finances",
        client=FAKE_CLIENT,
        json_out=cache_dir,
    )

    assert "julies-finances" in (vault / "wiki" / "log.md").read_text(encoding="utf-8")
    assert "- [[julies-finances]] — Index summary line." in (
        vault / "wiki" / "index.md"
    ).read_text(encoding="utf-8")


def test_cli_dry_run_prints_summary_without_writes(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    vault = tmp_path / "vault"
    _write_topic(vault)
    _write_source(vault, "source-one.md", "Julie finances has one sourced quote.")
    cache_dir = tmp_path / "cache"
    _write_cache(cache_dir, vault)
    _patch_model(monkeypatch, _default_result())
    before = _snapshot_tree(vault)

    exit_code = synthesize_topic.main(
        [
            "--vault",
            str(vault),
            "--topic",
            "julies-finances",
            "--dry-run",
            "--json-out",
            str(cache_dir),
        ],
        client=FAKE_CLIENT,
    )

    assert exit_code == 0
    assert "dry-run" in capsys.readouterr().out
    assert _snapshot_tree(vault) == before
