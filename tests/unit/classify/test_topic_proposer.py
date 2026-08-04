"""U6 topic proposer tests. RED-first per unit; the module is built incrementally.

Unit 1: gather notes matching no registered topic (recency-windowed, deduped).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import hashlib
from types import SimpleNamespace

from scripts.classify.topic_proposer import (
    NoteRef,
    ProposerConfig,
    TopicProposal,
    classify_clusters,
    cluster_notes,
    cluster_signature,
    filter_alias_collisions,
    gather_unregistered_notes,
    create_topic_stubs,
    propose_topic_metadata,
    resolve_collisions,
    score_cluster,
)
from scripts.classify.topics import Topic, load_topics, validate


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


class TestNamingAndSafety:
    @staticmethod
    def _cluster(person: str, tokens: set[str], n: int = 3):
        return cluster_notes(
            [_ref(f"{person}{i}.md", people={person}, tokens=tokens) for i in range(n)]
        )[0]

    @staticmethod
    def _topic(slug: str, aliases: list[str]) -> Topic:
        return Topic(slug=slug, aliases=aliases, status="active", path=Path(f"{slug}.md"))

    def test_signature_stable_for_same_members_distinct_otherwise(self) -> None:
        c1 = self._cluster("connor", {"homework"})
        c2 = self._cluster("connor", {"homework"})
        c3 = self._cluster("bob", {"tennis"})

        assert cluster_signature(c1) == cluster_signature(c2)
        assert cluster_signature(c1) != cluster_signature(c3)

    def test_llm_naming_used_when_available(self, monkeypatch) -> None:
        import scripts.classify.topic_proposer as tp

        def fake_generate_structured(**kwargs):
            return SimpleNamespace(
                name="Connor — behaviour",
                aliases=["Connor behaviour", "Connor discipline"],
                description="Notes about Connor's behaviour.",
            )

        monkeypatch.setattr(tp, "generate_structured", fake_generate_structured)
        proposal = propose_topic_metadata(
            self._cluster("connor", {"homework"}), client=object(), lm_available=True
        )

        assert proposal.source == "llm"
        assert proposal.name == "Connor — behaviour"
        assert "Connor discipline" in proposal.aliases
        assert proposal.slug == "connor-behaviour"

    def test_fallback_naming_when_lm_unavailable(self) -> None:
        proposal = propose_topic_metadata(
            self._cluster("connor", {"homework"}), client=None, lm_available=False
        )

        assert proposal.source == "fallback"
        assert "connor" in proposal.slug
        assert proposal.aliases  # never empty

    def test_fallback_when_structured_output_errors(self, monkeypatch) -> None:
        import scripts.classify.topic_proposer as tp
        from scripts.classify.structured_output import StructuredOutputError

        def boom(**kwargs):
            raise StructuredOutputError("no json")

        monkeypatch.setattr(tp, "generate_structured", boom)
        proposal = propose_topic_metadata(
            self._cluster("connor", {"homework"}), client=object(), lm_available=True
        )

        assert proposal.source == "fallback"

    def test_filter_alias_collisions_drops_existing(self) -> None:
        existing = [self._topic("budget", ["Budget", "spending"])]
        survivors = filter_alias_collisions(["budget", "Mortgage"], existing)

        assert survivors == ["Mortgage"]  # casefold collision dropped

    def test_resolve_new_vs_new_alias_collision(self) -> None:
        c = self._cluster("connor", {"homework"})
        p1 = TopicProposal(
            signature="s1", slug="one", name="One", aliases=("Shared", "OnlyOne"),
            description="", source="fallback", cluster=c,
        )
        p2 = TopicProposal(
            signature="s2", slug="two", name="Two", aliases=("shared",),
            description="", source="fallback", cluster=c,
        )

        accepted, rejected = resolve_collisions([p1, p2], existing_topics=[])

        # p1 keeps both; p2's only alias collides with p1 → p2 rejected.
        assert [p.slug for p in accepted] == ["one"]
        assert [p.slug for p in rejected] == ["two"]

    def test_resolve_rejects_slug_collision_with_existing(self) -> None:
        c = self._cluster("connor", {"homework"})
        existing = [self._topic("dup", ["Existing"])]
        p = TopicProposal(
            signature="s", slug="dup", name="Dup", aliases=("Fresh",),
            description="", source="fallback", cluster=c,
        )

        accepted, rejected = resolve_collisions([p], existing_topics=existing)

        assert accepted == []
        assert [p.slug for p in rejected] == ["dup"]

    def test_accepted_union_passes_strict_validate(self) -> None:
        c = self._cluster("connor", {"homework"})
        existing = [self._topic("budget", ["Budget"])]
        p = TopicProposal(
            signature="s", slug="connor", name="Connor", aliases=("Connor", "Budget"),
            description="", source="fallback", cluster=c,
        )

        accepted, _ = resolve_collisions([p], existing_topics=existing)
        union = existing + [
            Topic(slug=p.slug, aliases=list(p.aliases), status="active", path=Path("x.md"))
            for p in accepted
        ]
        validate(union)  # must not raise — "Budget" was dropped from the proposal


def _dummy_cluster():
    return cluster_notes(
        [_ref(f"d{i}.md", people={"connor"}, tokens={"homework"}) for i in range(3)]
    )[0]


def _proposal(slug: str, aliases: list[str], name: str | None = None) -> TopicProposal:
    return TopicProposal(
        signature="sig:" + slug,
        slug=slug,
        name=name or slug,
        aliases=tuple(aliases),
        description="desc",
        source="llm",
        cluster=_dummy_cluster(),
    )


class TestCreateStubs:
    def test_writes_valid_active_stub(self, tmp_path: Path) -> None:
        (tmp_path / "wiki" / "topics").mkdir(parents=True)

        res = create_topic_stubs(
            tmp_path, [_proposal("connor-behaviour", ["Connor behaviour", "Connor"])]
        )

        assert [p.slug for p in res.created] == ["connor-behaviour"]
        assert (tmp_path / "wiki" / "topics" / "connor-behaviour.md").exists()
        topics = load_topics(tmp_path)
        assert any(t.slug == "connor-behaviour" and t.status == "active" for t in topics)

    def test_never_overwrites_existing_slug(self, tmp_path: Path) -> None:
        d = tmp_path / "wiki" / "topics"
        d.mkdir(parents=True)
        (d / "foo.md").write_text(
            "---\ntype: topic\nslug: foo\naliases: [Original]\nstatus: active\n---\nkeep\n",
            encoding="utf-8",
        )
        before = (d / "foo.md").read_bytes()

        res = create_topic_stubs(tmp_path, [_proposal("foo", ["New"])])

        assert res.created == []
        assert [p.slug for p in res.skipped] == ["foo"]
        assert (d / "foo.md").read_bytes() == before

    def test_dry_run_writes_nothing(self, tmp_path: Path) -> None:
        (tmp_path / "wiki" / "topics").mkdir(parents=True)

        res = create_topic_stubs(tmp_path, [_proposal("x-topic", ["X"])], dry_run=True)

        assert not (tmp_path / "wiki" / "topics" / "x-topic.md").exists()
        assert [p.slug for p in res.would_create] == ["x-topic"]

    def test_unsafe_slug_is_rejected(self, tmp_path: Path) -> None:
        (tmp_path / "wiki" / "topics").mkdir(parents=True)

        res = create_topic_stubs(tmp_path, [_proposal("../evil", ["E"])])

        assert res.created == []
        assert not (tmp_path / "evil.md").exists()
        assert not (tmp_path / "wiki" / "evil.md").exists()

    def test_additive_only_leaves_source_notes_untouched(self, tmp_path: Path) -> None:
        (tmp_path / "wiki" / "topics").mkdir(parents=True)
        note = tmp_path / "note.md"
        note.write_text("---\ntype: note\n---\nbody\n", encoding="utf-8")
        before = hashlib.sha256(note.read_bytes()).hexdigest()

        create_topic_stubs(tmp_path, [_proposal("t-opic", ["T"])])

        assert hashlib.sha256(note.read_bytes()).hexdigest() == before

    def test_post_write_self_check_rolls_back_on_collision(self, tmp_path: Path) -> None:
        d = tmp_path / "wiki" / "topics"
        d.mkdir(parents=True)
        (d / "aaa.md").write_text(
            "---\ntype: topic\nslug: aaa\naliases: [Shared]\nstatus: active\n---\n",
            encoding="utf-8",
        )
        # Bypass resolve_collisions: a colliding stub reaches the writer.
        res = create_topic_stubs(tmp_path, [_proposal("zzz", ["Shared"])])

        assert not (d / "zzz.md").exists()  # rolled back
        assert [p.slug for p in res.rolled_back] == ["zzz"]
        assert any(t.slug == "aaa" for t in load_topics(tmp_path))  # vault still loads
