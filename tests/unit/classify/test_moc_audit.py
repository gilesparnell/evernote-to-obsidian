from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture()
def moc_audit():
    from scripts.classify import moc_audit

    return moc_audit


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _snapshot_tree(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _note(name: str, up: str) -> str:
    return (
        "---\n"
        "type: note\n"
        "org: Personal\n"
        "context: personal\n"
        f"up: {up}\n"
        "---\n\n"
        f"# {name}\n"
    )


class TestMissingMocs:
    def test_reports_missing_moc_with_two_refs_and_omits_existing_moc(
        self, moc_audit, tmp_path: Path
    ) -> None:
        vault = tmp_path / "Personal"
        _write(vault / "Meetings.md", "# Existing Meetings\n")
        _write(vault / "Alpha.md", _note("Alpha", "[[Technical]]"))
        _write(vault / "Beta.md", _note("Beta", "[[Technical]]"))
        _write(vault / "Gamma.md", _note("Gamma", "[[Meetings]]"))

        report = moc_audit.render_reports(
            [moc_audit.audit_vault(vault=vault, apply=False)]
        )

        assert "Vault: Personal" in report
        assert "Missing MOCs" in report
        assert "Technical — 2 incoming references" in report
        assert "# Technical" in report
        assert "Meetings —" not in report

    @pytest.mark.parametrize(
        "up",
        ["[[Meetings]]", "Meetings", "[[Meetings|alias]]", "Meetings.md"],
    )
    def test_up_variants_parse_to_same_moc(
        self, moc_audit, tmp_path: Path, up: str
    ) -> None:
        vault = tmp_path / "Personal"
        _write(vault / "Source.md", _note("Source", up))

        result = moc_audit.audit_vault(vault=vault, apply=False)

        assert result.missing_mocs["Meetings"].incoming_count == 1

    def test_output_order_is_sorted_by_moc_name(self, moc_audit, tmp_path: Path) -> None:
        vault = tmp_path / "Personal"
        _write(vault / "Tech note.md", _note("Tech note", "[[Technical]]"))
        _write(vault / "Career note.md", _note("Career note", "[[Career]]"))

        report = moc_audit.render_reports(
            [moc_audit.audit_vault(vault=vault, apply=False)]
        )

        assert report.index("Career — 1 incoming references") < report.index(
            "Technical — 1 incoming references"
        )


class TestApply:
    def test_dry_run_creates_nothing(self, moc_audit, tmp_path: Path) -> None:
        vault = tmp_path / "Personal"
        _write(vault / "Alpha.md", _note("Alpha", "[[Meetings]]"))
        before = _snapshot_tree(vault)

        moc_audit.audit_vault(vault=vault, apply=False)

        assert _snapshot_tree(vault) == before

    def test_apply_creates_only_referenced_missing_mocs_and_never_overwrites(
        self, moc_audit, tmp_path: Path
    ) -> None:
        vault = tmp_path / "Business"
        existing = "PINNED EXISTING CONTENT\n"
        _write(vault / "Meetings.md", existing)
        _write(vault / "Alpha.md", _note("Alpha", "[[Technical]]"))
        _write(vault / "Beta.md", _note("Beta", "[[Meetings]]"))

        result = moc_audit.audit_vault(vault=vault, apply=True)

        assert result.missing_mocs["Technical"].status == "created"
        assert result.missing_mocs["Career"].status == "skipped (no references)"
        assert (vault / "Technical.md").read_text(encoding="utf-8") == (
            "---\n"
            "type: moc\n"
            "org: Business\n"
            "context: work\n"
            "up: '[[Personal]]'\n"
            "tags: [moc]\n"
            "---\n\n"
            "# Technical\n\n"
            "Hub note — target of `up: [[Technical]]` links.\n\n"
            "## Inbox\n\n"
            "```dataview\n"
            "LIST WHERE up = this.file.link SORT file.name ASC\n"
            "```\n\n"
            "## Organised\n\n"
            "<!-- curated content goes here -->\n"
        )
        assert not (vault / "Career.md").exists()
        assert (vault / "Meetings.md").read_text(encoding="utf-8") == existing


class TestFrontmatterLint:
    def test_flags_self_referential_and_dangling_up_on_existing_mocs(
        self, moc_audit, tmp_path: Path
    ) -> None:
        vault = tmp_path / "Personal"
        _write(vault / "Personal.md", _note("Personal", "'[[Personal]]'"))
        _write(vault / "Interview Prep.md", _note("Interview Prep", "'[[Career]]'"))

        report = moc_audit.render_reports(
            [moc_audit.audit_vault(vault=vault, apply=False)]
        )

        assert "Frontmatter lint" in report
        assert "Personal.md: up points to itself ([[Personal]])" in report
        assert (
            "Interview Prep.md: up points to missing page [[Career]]"
            in report
        )
