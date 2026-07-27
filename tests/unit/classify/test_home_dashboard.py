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
def empty_vault(tmp_path: Path) -> Path:
    target = tmp_path / "Business"
    (target / "wiki" / "topics").mkdir(parents=True)
    return target


@pytest.fixture()
def home_dashboard():
    from scripts.classify import home_dashboard

    return home_dashboard


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


class TestHomeSectionTopics:
    def test_renders_topic_freshness_rows_from_cache(
        self, home_dashboard, vault: Path, tmp_path: Path
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

        section = home_dashboard.build_home_section(
            vault=vault,
            json_out=tmp_path,
            run_state={"complete": True},
        )

        assert section.startswith("## Topics & synthesis\n")
        assert "| Topic | Sources | Last synthesis | Changed |" in section
        assert "| julie-finances | 1 | 2026-07-20 | yes |" in section
        assert "| estate-legal | n/a | n/a | n/a |" in section

    def test_vault_with_no_topics_renders_empty_state_without_table(
        self, home_dashboard, empty_vault: Path, tmp_path: Path
    ) -> None:
        section = home_dashboard.build_home_section(
            vault=empty_vault,
            json_out=tmp_path,
            run_state={},
        )

        assert "No topics registered yet." in section
        assert "| Topic | Sources | Last synthesis | Changed |" not in section


class TestHomeStatusLine:
    def test_renders_all_existing_status_parts(
        self, home_dashboard, vault: Path, tmp_path: Path
    ) -> None:
        _write(vault / "wiki" / "gardener.md", "Intro\nHealth score: 75/100\n")
        _write(vault / "wiki" / "index.md", "# Wiki\n")
        _write(
            vault / "classification-review.md",
            "| Note | Reason |\n"
            "|---|---|\n"
            "| [[Needs Review]] | low confidence |\n"
            "| [[Still Queued]] | missing type |\n",
        )

        section = home_dashboard.build_home_section(
            vault=vault,
            json_out=tmp_path,
            run_state={},
        )

        assert (
            "Health 75/100 · [Gardener report](wiki/gardener.md) · "
            "[Wiki index](wiki/index.md) · Review queue: 2"
        ) in section

    @pytest.mark.parametrize(
        ("missing", "absent"),
        [
            (
                "gardener.md",
                ("Health 88/100", "[Gardener report](wiki/gardener.md)"),
            ),
            ("index.md", ("[Wiki index](wiki/index.md)",)),
            ("classification-review.md", ("Review queue:",)),
        ],
    )
    def test_omits_status_parts_for_missing_files(
        self,
        home_dashboard,
        vault: Path,
        tmp_path: Path,
        missing: str,
        absent: tuple[str, ...],
    ) -> None:
        _write(vault / "wiki" / "gardener.md", "Health score: 88/100\n")
        _write(vault / "wiki" / "index.md", "# Wiki\n")
        _write(vault / "classification-review.md", "- needs review\n")
        if missing == "gardener.md":
            (vault / "wiki" / "gardener.md").unlink()
        elif missing == "index.md":
            (vault / "wiki" / "index.md").unlink()
        else:
            (vault / "classification-review.md").unlink()

        section = home_dashboard.build_home_section(
            vault=vault,
            json_out=tmp_path,
            run_state={},
        )

        for needle in absent:
            assert needle not in section


class TestHomeWriting:
    def test_missing_home_creates_shell_with_generated_region(
        self, home_dashboard, empty_vault: Path
    ) -> None:
        home_dashboard.write_home(
            vault=empty_vault,
            section_md="## Topics & synthesis\nNo topics registered yet.\n",
            dry_run=False,
        )

        text = (empty_vault / "Home.md").read_text(encoding="utf-8")
        assert text.startswith("---\ntype: dashboard\n---\n\n# Home\n\n")
        assert "<!-- @generated:start -->\n" in text
        assert "## Topics & synthesis\nNo topics registered yet.\n" in text
        assert "<!-- @generated:end -->\n" in text

    def test_existing_home_replaces_only_generated_region(
        self, home_dashboard, vault: Path
    ) -> None:
        before = (
            "---\n"
            "type: dashboard\n"
            "---\n\n"
            "# Home\n\n"
            "Operator content above.\n\n"
            "<!-- @generated:start -->\n"
            "Old generated body.\n"
            "<!-- @generated:end -->\n\n"
            "Operator content below.\n"
        )
        _write(vault / "Home.md", before)

        home_dashboard.write_home(
            vault=vault,
            section_md="## Topics & synthesis\nNew generated body.\n",
            dry_run=False,
        )

        text = (vault / "Home.md").read_text(encoding="utf-8")
        assert text.startswith(
            "---\n"
            "type: dashboard\n"
            "---\n\n"
            "# Home\n\n"
            "Operator content above.\n\n"
        )
        assert "Old generated body." not in text
        assert "## Topics & synthesis\nNew generated body.\n" in text
        assert text.endswith("<!-- @generated:end -->\n\nOperator content below.\n")

    def test_dry_run_writes_nothing_byte_identical_tree(
        self, home_dashboard, vault: Path
    ) -> None:
        _write(vault / "Home.md", "# Home\n")
        before = _snapshot_tree(vault)

        home_dashboard.write_home(
            vault=vault,
            section_md="## Topics & synthesis\nWould write.\n",
            dry_run=True,
        )

        assert _snapshot_tree(vault) == before
