"""Unit tests for scripts.classify.frontmatter.

Tests the read/write/is_classified API for safe, idempotent frontmatter
handling on Obsidian markdown notes. Covers all eight scenarios called out
in the plan plus a few obvious edges (field order, key-collision merge,
file with no frontmatter).
"""

from pathlib import Path

import pytest

from scripts.classify.frontmatter import (
    is_classified,
    read_frontmatter,
    write_frontmatter,
)


class TestReadFrontmatter:
    def test_returns_empty_dict_when_no_frontmatter(self, tmp_path: Path) -> None:
        note = tmp_path / "plain.md"
        note.write_text("Just body content, no frontmatter.\n", encoding="utf-8")
        assert read_frontmatter(note) == {}

    def test_parses_existing_string_fields(self, tmp_path: Path) -> None:
        note = tmp_path / "n.md"
        note.write_text(
            '---\ntitle: "My Note"\ngranola_id: abc-123\n---\n\nBody.\n',
            encoding="utf-8",
        )
        fm = read_frontmatter(note)
        assert fm["title"] == "My Note"
        assert fm["granola_id"] == "abc-123"

    def test_parses_array_values(self, tmp_path: Path) -> None:
        note = tmp_path / "n.md"
        note.write_text(
            '---\npeople: ["Alice Smith", "Bob Jones"]\ntags: ["star", "draft"]\n---\n\nBody.\n',
            encoding="utf-8",
        )
        fm = read_frontmatter(note)
        assert fm["people"] == ["Alice Smith", "Bob Jones"]
        assert fm["tags"] == ["star", "draft"]


class TestWriteFrontmatter:
    def test_creates_frontmatter_block_when_absent(self, tmp_path: Path) -> None:
        note = tmp_path / "n.md"
        note.write_text("Just body.\n", encoding="utf-8")
        write_frontmatter(note, {"type": "meeting", "org": "Amazon"})
        text = note.read_text(encoding="utf-8")
        assert text.startswith("---\n")
        fm = read_frontmatter(note)
        assert fm["type"] == "meeting"
        assert fm["org"] == "Amazon"
        assert "Just body." in text

    def test_merges_without_clobbering_existing_fields(self, tmp_path: Path) -> None:
        note = tmp_path / "n.md"
        note.write_text(
            '---\ntitle: "Original"\ngranola_id: keep-me\n---\n\nBody.\n',
            encoding="utf-8",
        )
        write_frontmatter(note, {"type": "meeting", "org": "Amazon"})
        fm = read_frontmatter(note)
        assert fm["title"] == "Original"
        assert fm["granola_id"] == "keep-me"
        assert fm["type"] == "meeting"
        assert fm["org"] == "Amazon"

    def test_new_fields_win_on_collision(self, tmp_path: Path) -> None:
        note = tmp_path / "n.md"
        note.write_text(
            '---\ntype: note\n---\n\nBody.\n',
            encoding="utf-8",
        )
        write_frontmatter(note, {"type": "meeting"})
        fm = read_frontmatter(note)
        assert fm["type"] == "meeting"

    def test_preserves_body_content(self, tmp_path: Path) -> None:
        note = tmp_path / "n.md"
        body = "# Heading\n\nSome **markdown** body.\n\n- list item\n"
        note.write_text(f"---\ntitle: X\n---\n\n{body}", encoding="utf-8")
        write_frontmatter(note, {"type": "note"})
        text = note.read_text(encoding="utf-8")
        assert "# Heading" in text
        assert "**markdown**" in text
        assert "- list item" in text

    def test_field_order_existing_first_then_new(self, tmp_path: Path) -> None:
        note = tmp_path / "n.md"
        note.write_text(
            '---\ntitle: X\ngranola_id: abc\n---\n\nbody\n',
            encoding="utf-8",
        )
        write_frontmatter(note, {"type": "meeting", "org": "Amazon"})
        text = note.read_text(encoding="utf-8")
        # Slice the frontmatter block (between first --- and second ---).
        fm_block = text.split("---", 2)[1]
        assert fm_block.index("title:") < fm_block.index("granola_id:")
        assert fm_block.index("granola_id:") < fm_block.index("type:")
        assert fm_block.index("type:") < fm_block.index("org:")

    def test_atomic_write_leaves_no_tmp_file(self, tmp_path: Path) -> None:
        note = tmp_path / "n.md"
        note.write_text("body\n", encoding="utf-8")
        write_frontmatter(note, {"type": "meeting", "org": "Amazon"})
        siblings = list(tmp_path.iterdir())
        assert all(not p.name.endswith(".tmp") for p in siblings), (
            f"Found lingering .tmp file: {[p.name for p in siblings]}"
        )


class TestIsClassified:
    def _required_fm(self) -> str:
        return (
            "---\n"
            "type: meeting\n"
            "org: Amazon\n"
            "context: work\n"
            'up: "[[Meetings]]"\n'
            "---\n\nbody.\n"
        )

    def test_false_when_no_frontmatter(self, tmp_path: Path) -> None:
        note = tmp_path / "n.md"
        note.write_text("just body\n", encoding="utf-8")
        assert is_classified(note) is False

    def test_false_when_type_missing(self, tmp_path: Path) -> None:
        note = tmp_path / "n.md"
        note.write_text(
            '---\norg: Amazon\ncontext: work\nup: "[[Meetings]]"\n---\n\nbody.\n',
            encoding="utf-8",
        )
        assert is_classified(note) is False

    def test_true_when_all_required_present(self, tmp_path: Path) -> None:
        note = tmp_path / "n.md"
        note.write_text(self._required_fm(), encoding="utf-8")
        assert is_classified(note) is True

    def test_true_when_optional_people_and_project_absent(self, tmp_path: Path) -> None:
        note = tmp_path / "n.md"
        # Same as _required_fm() — people/project are NOT required for is_classified.
        note.write_text(self._required_fm(), encoding="utf-8")
        assert is_classified(note) is True

    def test_false_when_only_some_required_present(self, tmp_path: Path) -> None:
        note = tmp_path / "n.md"
        note.write_text(
            '---\ntype: meeting\norg: Amazon\n---\n\nbody.\n',
            encoding="utf-8",
        )
        assert is_classified(note) is False
