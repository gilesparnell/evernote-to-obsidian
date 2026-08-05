from __future__ import annotations

import json
from pathlib import Path
from shutil import copytree

import pytest


FIXTURE_VAULT = Path(__file__).resolve().parents[2] / "fixtures" / "chain"


@pytest.fixture()
def vault(tmp_path: Path) -> Path:
    target = tmp_path / "Personal"
    copytree(FIXTURE_VAULT, target)
    return target


@pytest.fixture()
def business_vault(tmp_path: Path) -> Path:
    target = tmp_path / "Business"
    target.mkdir()
    (target / "wiki" / "topics").mkdir(parents=True)
    return target


@pytest.fixture()
def gardener():
    from scripts.classify import gardener

    return gardener


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _snapshot_tree(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _cache(json_out: Path, vault: Path, slug: str, data: dict) -> None:
    _write(json_out / f"{vault.name}-{slug}.json", json.dumps(data, indent=2) + "\n")


class TestGardenerVaultMetrics:
    def test_reports_coverage_orphans_queue_and_exhaust_against_chain_fixture(
        self, gardener, vault: Path, tmp_path: Path
    ) -> None:
        _write(
            vault / "Classified with orphan up.md",
            "---\n"
            "type: note\n"
            "org: Personal\n"
            "context: home\n"
            "up: Missing Parent\n"
            "---\n\n"
            "A classified note whose parent page does not exist.\n",
        )
        _write(
            vault / "Classified linked up.md",
            "---\n"
            "type: note\n"
            "org: Personal\n"
            "context: home\n"
            "up: Existing Parent\n"
            "---\n\n"
            "A classified note whose parent exists.\n",
        )
        _write(vault / "Existing Parent.md", "# Existing Parent\n")
        _write(vault / "classification-review.md", "- needs review\n- still queued\n")
        _write(vault / "classification-review-2026-07-20.html", "<html></html>\n")

        report = gardener.build_report(
            vaults=[vault],
            run_state={"complete": True, "steps": {}},
            json_out=tmp_path,
        )

        assert "| Personal | 2 / 12 | 16.7% | 10 | 1 | 2 | 1 |" in report
        assert "classification-review-2026-07-20.html" in report

    def test_includes_both_vaults_in_one_report(
        self, gardener, vault: Path, business_vault: Path, tmp_path: Path
    ) -> None:
        _write(
            business_vault / "Business classified.md",
            "---\n"
            "type: note\n"
            "org: Business\n"
            "context: client\n"
            "up: Business Hub\n"
            "---\n\n"
            "Business note.\n",
        )

        report = gardener.build_report(
            vaults=[vault, business_vault],
            run_state={"complete": True, "steps": {}},
            json_out=tmp_path,
        )

        assert "| Personal |" in report
        assert "| Business |" in report


class TestGardenerExhaustLinks:
    def test_exhaust_entry_renders_as_clickable_file_uri_link(
        self, gardener, vault: Path, tmp_path: Path
    ) -> None:
        exhaust = vault / "classification-review-2026-07-20.html"
        _write(exhaust, "<html></html>\n")

        report = gardener.build_report(
            vaults=[vault],
            run_state={"complete": True, "steps": {}},
            json_out=tmp_path,
        )

        expected = (
            f"- Personal: [classification-review-2026-07-20.html]"
            f"({exhaust.resolve().as_uri()})"
        )
        assert expected in report

    def test_exhaust_link_percent_encodes_spaces_in_vault_path(
        self, gardener, tmp_path: Path
    ) -> None:
        spaced_vault = tmp_path / "My Vault"
        spaced_vault.mkdir()
        exhaust = spaced_vault / "classification-review.html"
        _write(exhaust, "<html></html>\n")

        report = gardener.build_report(
            vaults=[spaced_vault],
            run_state={"complete": True, "steps": {}},
            json_out=tmp_path,
        )

        assert f"({exhaust.resolve().as_uri()})" in report
        assert "My%20Vault" in report

    def test_vault_without_exhaust_keeps_plain_none_line(
        self, gardener, vault: Path, tmp_path: Path
    ) -> None:
        report = gardener.build_report(
            vaults=[vault],
            run_state={"complete": True, "steps": {}},
            json_out=tmp_path,
        )

        assert "- Personal: none" in report


class TestGardenerRunState:
    def test_interrupted_run_renders_complete_false_and_step_table(
        self, gardener, vault: Path, tmp_path: Path
    ) -> None:
        report = gardener.build_report(
            vaults=[vault],
            run_state={
                "started_at": "2026-07-13T23:00:04+10:00",
                "mode": "nightly",
                "complete": False,
                "steps": {
                    "export": {"status": "ok", "detail": "3 new notes"},
                    "synthesize": {"status": "degraded", "detail": "LM unreachable"},
                },
            },
            json_out=tmp_path,
        )

        assert "| Complete | false |" in report
        assert "| export | ok | 3 new notes |" in report
        assert "| synthesize | degraded | LM unreachable |" in report

    def test_missing_and_partial_run_state_render_na_and_never_crash(
        self, gardener, vault: Path, tmp_path: Path
    ) -> None:
        missing = gardener.build_report(vaults=[vault], run_state={}, json_out=tmp_path)
        partial = gardener.build_report(
            vaults=[vault],
            run_state={"steps": {"classify": {}}},
            json_out=tmp_path,
        )

        assert "| Started | n/a |" in missing
        assert "| Mode | n/a |" in missing
        assert "| Complete | n/a |" in missing
        assert "| classify | n/a | n/a |" in partial


class TestGardenerTopicFreshness:
    def test_topic_freshness_rows_include_source_count_date_and_hash_status(
        self, gardener, vault: Path, tmp_path: Path
    ) -> None:
        topic = vault / "wiki" / "topics" / "julie-finances.md"
        topic.write_text(
            "---\n"
            "type: topic\n"
            "slug: julie-finances\n"
            "aliases: [\"Julie finances\"]\n"
            "status: active\n"
            "updated: 2026-07-20\n"
            "source_set_hash: sha256:old\n"
            "---\n\n"
            "# Julie finances\n",
            encoding="utf-8",
        )
        _cache(
            tmp_path,
            vault,
            "julie-finances",
            {
                "source_set_hash": "sha256:new",
                "sources": [{"path": "Julie finances title match.md"}],
            },
        )

        report = gardener.build_report(
            vaults=[vault],
            run_state={"complete": True, "steps": {}},
            json_out=tmp_path,
        )

        assert "| Personal | julie-finances | 1 | 2026-07-20 | yes |" in report
        assert "| Personal | estate-legal | n/a | n/a | n/a |" in report


class TestGardenerHealthScore:
    def test_health_score_bounds_at_zero_and_one_hundred(self, gardener) -> None:
        assert set(gardener.HEALTH_SCORE_WEIGHTS) == {
            "run_complete",
            "coverage",
            "no_orphans",
            "no_review_queue",
            "no_exhaust",
            "fresh_topics",
        }
        assert sum(gardener.HEALTH_SCORE_WEIGHTS.values()) == 100

        assert gardener._health_score(
            run_complete=True,
            coverage_ratio=1.0,
            orphan_count=0,
            review_queue_count=0,
            exhaust_count=0,
            stale_topic_count=0,
            topic_count=2,
        ) == 100
        assert gardener._health_score(
            run_complete=False,
            coverage_ratio=0.0,
            orphan_count=3,
            review_queue_count=4,
            exhaust_count=2,
            stale_topic_count=2,
            topic_count=2,
        ) == 0


class TestGardenerWriting:
    def test_write_report_preserves_user_region_round_trip(
        self, gardener, vault: Path
    ) -> None:
        target = vault / "wiki" / "gardener.md"
        _write(
            target,
            "---\n"
            "type: gardener-report\n"
            "updated: old\n"
            "---\n\n"
            "# Gardener\n\n"
            "<!-- @generated:start -->\n"
            "Old generated body.\n"
            "<!-- @generated:end -->\n\n"
            "<!-- @user:start -->\n"
            "Keep this operator note.\n"
            "<!-- @user:end -->\n",
        )

        gardener.write_report(vault=vault, report_md="New generated body.\n")

        text = target.read_text(encoding="utf-8")
        assert "New generated body." in text
        assert "Old generated body." not in text
        assert "<!-- @user:start -->\nKeep this operator note.\n<!-- @user:end -->" in text

    def test_dry_run_writes_nothing_byte_identical_tree(
        self, gardener, vault: Path
    ) -> None:
        before = _snapshot_tree(vault)

        gardener.write_report(vault=vault, report_md="Would write.\n", dry_run=True)

        assert _snapshot_tree(vault) == before


class TestLMStudioRow:
    def test_lm_studio_row_renders_all_three_states(
        self, gardener, vault: Path, tmp_path: Path
    ) -> None:
        missing = gardener.build_report(vaults=[vault], run_state={}, json_out=tmp_path)
        assert "| LM Studio | n/a |" in missing

        down = gardener.build_report(
            vaults=[vault],
            run_state={"lm_studio": {"available": False, "reason": "connection refused"}},
            json_out=tmp_path,
        )
        assert "| LM Studio | NOT AVAILABLE — connection refused |" in down

        up = gardener.build_report(
            vaults=[vault],
            run_state={"lm_studio": {"available": True, "models": ["google/gemma-4-e4b"]}},
            json_out=tmp_path,
        )
        assert "| LM Studio | available (google/gemma-4-e4b) |" in up


class TestGardenerProposerSections:
    """U6 Unit 7: the report is the only surface the operator reads, so every
    proposer outcome — created, proposed, ledgered, quarantined — lands here."""

    def _artifact(self, json_out: Path, vault: Path, **payload) -> None:
        base = {
            "generated_at": "2026-08-05T21:00:00+10:00",
            "auto_created": [],
            "proposed": [],
            "ledger_count": 0,
            "promoted": [],
        }
        base.update(payload)
        _write(json_out / f"{vault.name}-_proposer.json", json.dumps(base, indent=2) + "\n")

    def test_proposals_section_lists_each_proposed_topic(
        self, gardener, vault: Path, tmp_path: Path
    ) -> None:
        self._artifact(
            tmp_path,
            vault,
            proposed=[
                {
                    "slug": "school-lying",
                    "name": "School lying",
                    "aliases": ["lying at school", "Connor lying"],
                    "description": "Recurring lying incidents at school.",
                    "note_count": 4,
                    "members": ["a.md", "b.md"],
                    "source": "llm",
                }
            ],
        )

        report = gardener.build_report(
            vaults=[vault], run_state={"complete": True, "steps": {}}, json_out=tmp_path
        )

        assert "## Proposals" in report
        assert "Topic proposer is pending U6." not in report
        assert "| Personal | school-lying | School lying | 4 |" in report
        assert "lying at school" in report
        assert "Recurring lying incidents at school." in report

    def test_auto_created_section_links_created_topics(
        self, gardener, vault: Path, tmp_path: Path
    ) -> None:
        self._artifact(
            tmp_path,
            vault,
            auto_created=[{"slug": "school-lying", "name": "School lying", "note_count": 6}],
        )

        report = gardener.build_report(
            vaults=[vault], run_state={"complete": True, "steps": {}}, json_out=tmp_path
        )

        assert "## Auto-created" in report
        assert "- Personal: [[school-lying]] — School lying (6 notes)" in report

    def test_ledger_row_reports_tracked_count_and_promotions(
        self, gardener, vault: Path, tmp_path: Path
    ) -> None:
        self._artifact(
            tmp_path,
            vault,
            ledger_count=7,
            promoted=[{"key": "person:connor", "name": "Connor"}],
        )

        report = gardener.build_report(
            vaults=[vault], run_state={"complete": True, "steps": {}}, json_out=tmp_path
        )

        assert "## Ledger" in report
        assert "| Personal | 7 | Connor |" in report

    def test_empty_artifact_renders_explicit_nothing_not_a_blank_section(
        self, gardener, vault: Path, tmp_path: Path
    ) -> None:
        self._artifact(tmp_path, vault)

        report = gardener.build_report(
            vaults=[vault], run_state={"complete": True, "steps": {}}, json_out=tmp_path
        )

        assert "No proposals this run." in report
        assert "None auto-created this run." in report

    def test_missing_or_corrupt_artifact_never_crashes_the_report(
        self, gardener, vault: Path, tmp_path: Path
    ) -> None:
        missing = gardener.build_report(
            vaults=[vault], run_state={"complete": True, "steps": {}}, json_out=tmp_path
        )
        _write(tmp_path / f"{vault.name}-_proposer.json", "{not json")
        corrupt = gardener.build_report(
            vaults=[vault], run_state={"complete": True, "steps": {}}, json_out=tmp_path
        )

        assert "No proposals this run." in missing
        assert "No proposals this run." in corrupt

    def test_quarantine_section_flags_an_unloadable_topic_file(
        self, gardener, vault: Path, tmp_path: Path
    ) -> None:
        bad = vault / "wiki" / "topics" / "broken.md"
        _write(
            bad,
            "---\ntype: topic\nslug: not-broken\naliases: [x]\nstatus: active\n---\n",
        )

        report = gardener.build_report(
            vaults=[vault], run_state={"complete": True, "steps": {}}, json_out=tmp_path
        )

        assert "## Quarantine" in report
        assert "broken.md" in report
        assert "not-broken" in report

    def test_quarantine_section_lists_swept_conflict_copies(
        self, gardener, vault: Path, tmp_path: Path
    ) -> None:
        report = gardener.build_report(
            vaults=[vault],
            run_state={
                "complete": True,
                "steps": {},
                "topic_conflicts_swept": ["Personal/wiki/topics/julie-finances 2.md"],
            },
            json_out=tmp_path,
        )

        assert "julie-finances 2.md" in report

    def test_clean_vault_reports_no_quarantine(
        self, gardener, business_vault: Path, tmp_path: Path
    ) -> None:
        report = gardener.build_report(
            vaults=[business_vault], run_state={"complete": True, "steps": {}}, json_out=tmp_path
        )

        quarantine = report.split("## Quarantine", 1)[1]
        assert "- Business: none" in quarantine

    def test_gardener_report_is_never_visible_to_the_proposer(self, gardener, vault: Path) -> None:
        """R-7: the report must not become a source note the proposer clusters
        on, or the chain feeds on its own exhaust."""
        from scripts.classify.collect_topic import iter_source_notes

        gardener.write_report(vault=vault, report_md="# Gardener\n\nsome proposal text\n")

        assert (vault / "wiki" / "gardener.md").exists()
        assert not [p for p in iter_source_notes(vault) if p.name == "gardener.md"]


class TestGardenerDanglingRefs:
    """R-2: a raw-deleted topic leaves `topics: [[slug]]` refs pointing at
    nothing, and clicking one in Obsidian creates an empty note — the exact
    "zeroed notes" incident. The gardener FLAGS them and never prunes: it can't
    tell a deliberate delete from an iCloud placeholder or a mid-sync gap."""

    def test_ref_with_no_topic_file_is_flagged(
        self, gardener, business_vault: Path, tmp_path: Path
    ) -> None:
        _write(
            business_vault / "Meeting note.md",
            '---\ntype: note\ntopics: ["[[ghost-topic]]"]\n---\n\nbody\n',
        )

        report = gardener.build_report(
            vaults=[business_vault], run_state={"complete": True, "steps": {}}, json_out=tmp_path
        )

        section = report.split("## Dangling refs", 1)[1]
        assert "ghost-topic" in section
        assert "Meeting note.md" in section

    def test_nothing_is_pruned_when_a_ref_dangles(
        self, gardener, business_vault: Path, tmp_path: Path
    ) -> None:
        note = business_vault / "Meeting note.md"
        _write(note, '---\ntype: note\ntopics: ["[[ghost-topic]]"]\n---\n\nbody\n')
        before = _snapshot_tree(business_vault)

        gardener.build_report(
            vaults=[business_vault], run_state={"complete": True, "steps": {}}, json_out=tmp_path
        )

        assert _snapshot_tree(business_vault) == before

    def test_a_rejected_tombstone_is_not_dangling(
        self, gardener, business_vault: Path, tmp_path: Path
    ) -> None:
        """The tombstone file still exists, so the backlink still resolves."""
        _write(
            business_vault / "wiki" / "topics" / "wrong-topic.md",
            "---\ntype: topic\nslug: wrong-topic\naliases: [x]\nstatus: rejected\n---\n",
        )
        _write(
            business_vault / "Meeting note.md",
            '---\ntype: note\ntopics: ["[[wrong-topic]]"]\n---\n\nbody\n',
        )

        report = gardener.build_report(
            vaults=[business_vault], run_state={"complete": True, "steps": {}}, json_out=tmp_path
        )

        section = report.split("## Dangling refs", 1)[1]
        assert "- Business: none" in section

    def test_clean_vault_reports_no_dangling_refs(
        self, gardener, business_vault: Path, tmp_path: Path
    ) -> None:
        report = gardener.build_report(
            vaults=[business_vault], run_state={"complete": True, "steps": {}}, json_out=tmp_path
        )

        assert "- Business: none" in report.split("## Dangling refs", 1)[1]

    def test_malformed_topics_value_never_crashes_the_report(
        self, gardener, business_vault: Path, tmp_path: Path
    ) -> None:
        _write(business_vault / "Bad.md", "---\ntype: note\ntopics: nope\n---\n\nbody\n")

        report = gardener.build_report(
            vaults=[business_vault], run_state={"complete": True, "steps": {}}, json_out=tmp_path
        )

        assert "## Dangling refs" in report
