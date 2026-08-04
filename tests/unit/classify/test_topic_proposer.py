"""U6 topic proposer tests. RED-first per unit; the module is built incrementally.

Unit 1: gather notes matching no registered topic (recency-windowed, deduped).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from scripts.classify.topic_proposer import (
    NoteRef,
    ProposerConfig,
    classify_clusters,
    cluster_notes,
    gather_unregistered_notes,
    score_cluster,
)


def _ref(
    rel: str,
    *,
    people: set[str] | None = None,
    tags: set[str] | None = None,
    org: str | None = None,
    tokens: set[str] | None = None,
) -> NoteRef:
    return NoteRef(
        path=Path(rel),
        rel=rel,
        title=rel,
        people=frozenset(people or set()),
        tags=frozenset(tags or set()),
        org=org,
        tokens=frozenset(tokens or set()),
    )


AEST = timezone(timedelta(hours=10))


def _topic(vault: Path, slug: str, aliases: list[str]) -> None:
    d = vault / "wiki" / "topics"
    d.mkdir(parents=True, exist_ok=True)
    alias_yaml = "[" + ", ".join(aliases) + "]"
    (d / f"{slug}.md").write_text(
        f"---\ntype: topic\nslug: {slug}\naliases: {alias_yaml}\nstatus: active\n---\n",
        encoding="utf-8",
    )


def _note(
    vault: Path,
    relpath: str,
    *,
    body: str = "",
    people: list[str] | None = None,
    tags: list[str] | None = None,
    org: str | None = None,
    updated: str | None = None,
) -> Path:
    path = vault / relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    fm = ["---", "type: note"]
    if people is not None:
        fm.append("people: [" + ", ".join(people) + "]")
    if tags is not None:
        fm.append("tags: [" + ", ".join(tags) + "]")
    if org is not None:
        fm.append(f"org: {org}")
    if updated is not None:
        fm.append(f"updated: {updated}")
    fm.append("---")
    path.write_text("\n".join(fm) + "\n\n" + body + "\n", encoding="utf-8")
    return path


def _rels(refs: list[NoteRef]) -> set[str]:
    return {r.rel for r in refs}


class TestGatherUnregistered:
    def test_excludes_notes_matching_a_topic_alias(self, tmp_path: Path) -> None:
        _topic(tmp_path, "finance", ["invoice"])
        _note(tmp_path, "matched.md", body="Paid the invoice today.")
        _note(tmp_path, "orphan.md", body="Planning a camping trip.")

        refs = gather_unregistered_notes(tmp_path, full=True)

        assert _rels(refs) == {"orphan.md"}

    def test_matching_is_filename_aware(self, tmp_path: Path) -> None:
        _topic(tmp_path, "finance", ["invoice"])
        _note(tmp_path, "Invoice reminder.md", body="nothing relevant here")

        refs = gather_unregistered_notes(tmp_path, full=True)

        assert _rels(refs) == set()

    def test_never_gathers_wiki_or_backup_notes(self, tmp_path: Path) -> None:
        _topic(tmp_path, "t", ["zzz"])
        _note(tmp_path, "wiki/entities/lisa.md", body="unmatched body")
        _note(tmp_path, "Personal-backup-2026/old.md", body="unmatched body")
        _note(tmp_path, "real.md", body="unmatched body")

        refs = gather_unregistered_notes(tmp_path, full=True)

        assert _rels(refs) == {"real.md"}

    def test_dedupes_yarle_numbered_copies_prefers_base(self, tmp_path: Path) -> None:
        _note(tmp_path, "Camp.md", body="identical camping body")
        _note(tmp_path, "Camp.1.md", body="identical camping body")

        refs = gather_unregistered_notes(tmp_path, full=True)

        assert _rels(refs) == {"Camp.md"}

    def test_recency_window_excludes_old_notes(self, tmp_path: Path) -> None:
        now = datetime(2026, 8, 5, 12, 0, tzinfo=AEST)
        _note(tmp_path, "fresh.md", body="fresh unmatched", updated="2026-08-01")
        _note(tmp_path, "stale.md", body="stale unmatched", updated="2026-01-01")

        refs = gather_unregistered_notes(tmp_path, recency_days=30, now=now)

        assert _rels(refs) == {"fresh.md"}

    def test_full_sweep_ignores_recency(self, tmp_path: Path) -> None:
        now = datetime(2026, 8, 5, 12, 0, tzinfo=AEST)
        _note(tmp_path, "stale.md", body="stale unmatched", updated="2026-01-01")

        refs = gather_unregistered_notes(tmp_path, recency_days=30, now=now, full=True)

        assert _rels(refs) == {"stale.md"}

    def test_noteref_carries_folded_signals(self, tmp_path: Path) -> None:
        _note(
            tmp_path,
            "n.md",
            body="Connor was lying about homework again",
            people=["Connor"],
            tags=["parenting"],
            org="Household",
        )

        refs = gather_unregistered_notes(tmp_path, full=True)

        ref = next(r for r in refs if r.rel == "n.md")
        assert "connor" in ref.people
        assert "parenting" in ref.tags
        assert "homework" in ref.tokens
        assert "connor" in ref.tokens


class TestClusterNotes:
    def test_three_notes_sharing_a_person_form_one_cluster(self) -> None:
        refs = [
            _ref("a.md", people={"connor"}, tokens={"homework", "lying", "school"}),
            _ref("b.md", people={"connor"}, tokens={"homework", "chores", "lying"}),
            _ref("c.md", people={"connor"}, tokens={"school", "lying", "phone"}),
        ]

        clusters = cluster_notes(refs)

        assert len(clusters) == 1
        assert {m.rel for m in clusters[0].members} == {"a.md", "b.md", "c.md"}

    def test_generic_tag_alone_forms_no_cluster(self) -> None:
        refs = [
            _ref("a.md", tags={"draft"}, tokens={"alpha"}),
            _ref("b.md", tags={"draft"}, tokens={"beta"}),
            _ref("c.md", tags={"draft"}, tokens={"gamma"}),
        ]

        assert cluster_notes(refs) == []

    def test_incidental_token_overlap_alone_forms_no_cluster(self) -> None:
        # Shared tokens but NO shared categorical anchor → no edge (AND-gate).
        refs = [
            _ref("a.md", people={"alice"}, tokens={"meeting", "notes"}),
            _ref("b.md", people={"bob"}, tokens={"meeting", "notes"}),
            _ref("c.md", people={"carol"}, tokens={"meeting", "notes"}),
        ]

        assert cluster_notes(refs) == []

    def test_singletons_and_pairs_are_not_clusters(self) -> None:
        refs = [
            _ref("a.md", people={"x"}),
            _ref("b.md", people={"x"}),  # only a pair share x
            _ref("c.md", people={"y"}),  # one-off
        ]

        assert cluster_notes(refs) == []

    def test_chain_does_not_weld_into_a_cluster(self) -> None:
        # a~b (share x), b~c (share y), a≁c → a 3-chain, not a clique.
        refs = [
            _ref("a.md", people={"x"}),
            _ref("b.md", people={"x", "y"}),
            _ref("c.md", people={"y"}),
        ]

        assert cluster_notes(refs) == []

    def test_two_distinct_themes_yield_two_clusters(self) -> None:
        refs = [
            _ref("a1.md", people={"alice"}, tokens={"budget"}),
            _ref("a2.md", people={"alice"}, tokens={"budget"}),
            _ref("a3.md", people={"alice"}, tokens={"budget"}),
            _ref("b1.md", people={"bob"}, tokens={"tennis"}),
            _ref("b2.md", people={"bob"}, tokens={"tennis"}),
            _ref("b3.md", people={"bob"}, tokens={"tennis"}),
        ]

        clusters = cluster_notes(refs)

        assert len(clusters) == 2
        sizes = sorted(len(c.members) for c in clusters)
        assert sizes == [3, 3]

    def test_cluster_exposes_anchors_and_cohesion(self) -> None:
        refs = [
            _ref("a.md", people={"connor"}, tokens={"homework", "lying"}),
            _ref("b.md", people={"connor"}, tokens={"homework", "lying"}),
            _ref("c.md", people={"connor"}, tokens={"homework", "chores"}),
        ]

        cluster = cluster_notes(refs)[0]

        assert "person:connor" in cluster.anchors
        assert cluster.anchor_density == 1.0
        assert 0.0 <= cluster.cohesion <= 1.0
        assert cluster.cohesion > 0.0  # they share real tokens


class TestConfidenceAndRouting:
    def _strong(self):
        # 5 notes sharing a person + heavily overlapping distinctive tokens.
        toks = {"mortgage", "offset", "refinance", "valuation"}
        return cluster_notes(
            [_ref(f"s{i}.md", people={"banker"}, tokens=toks) for i in range(5)]
        )[0]

    def _weak(self):
        # 3 notes sharing a person but with disjoint tokens (no text cohesion).
        return cluster_notes(
            [
                _ref("w0.md", people={"pal"}, tokens={"alpha"}),
                _ref("w1.md", people={"pal"}, tokens={"beta"}),
                _ref("w2.md", people={"pal"}, tokens={"gamma"}),
            ]
        )[0]

    def test_confidence_is_in_unit_range(self) -> None:
        assert 0.0 <= score_cluster(self._strong()) <= 1.0
        assert 0.0 <= score_cluster(self._weak()) <= 1.0

    def test_strong_cluster_outscores_weak(self) -> None:
        assert score_cluster(self._strong()) > score_cluster(self._weak())

    def test_geometric_mean_lets_weak_cohesion_veto_large_size(self) -> None:
        # Big cluster, strong anchor, but ~zero text cohesion.
        big = cluster_notes(
            [_ref(f"b{i}.md", people={"pal"}, tokens={f"uniq{i}"}) for i in range(8)]
        )[0]
        # Smaller but genuinely cohesive cluster.
        toks = {"reflux", "elimination", "dairy"}
        balanced = cluster_notes(
            [_ref(f"c{i}.md", people={"doc"}, tokens=toks) for i in range(4)]
        )[0]

        assert score_cluster(balanced) > score_cluster(big)

    def test_default_config_never_auto_creates(self) -> None:
        routing = classify_clusters([self._strong()], ProposerConfig())

        assert routing.auto == []
        assert len(routing.propose) + len(routing.ledger) == 1

    def test_lowered_auto_threshold_promotes_a_strong_cluster(self) -> None:
        cfg = ProposerConfig(auto_confidence=0.3)
        routing = classify_clusters([self._strong()], cfg)

        assert [sc.cluster for sc in routing.auto] == [self._strong()]

    def test_sub_floor_cluster_goes_to_ledger(self) -> None:
        cfg = ProposerConfig(auto_confidence=0.99, propose_floor=0.99)
        routing = classify_clusters([self._weak()], cfg)

        assert routing.propose == []
        assert len(routing.ledger) == 1

    def test_routing_partitions_every_cluster(self) -> None:
        clusters = [self._strong(), self._weak()]
        routing = classify_clusters(clusters, ProposerConfig(auto_confidence=0.5))

        total = len(routing.auto) + len(routing.propose) + len(routing.ledger)
        assert total == len(clusters)
