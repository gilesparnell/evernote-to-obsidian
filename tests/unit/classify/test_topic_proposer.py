"""U6 topic proposer tests. RED-first per unit; the module is built incrementally.

Unit 1: gather notes matching no registered topic (recency-windowed, deduped).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from scripts.classify.topic_proposer import NoteRef, gather_unregistered_notes


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
