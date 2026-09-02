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


class TestReadFrontmatterMalformedYAML:
    """Real Evernote exports emit unquoted titles that break yaml.safe_load.

    The parser must treat those notes as if they had no frontmatter (return
    an empty dict) rather than crash the pipeline. Patterns observed in
    Evernote/notes/AWS (2026-05-14, 1540/6375 notes affected):
      - title: 1-1: Stefan            (unquoted colon)
      - title: - Business Card        (leading dash → sequence)
      - title: * [[link]]             (leading asterisk → alias)
      - title: [Cancelled] Foo: Bar   (flow-mapping prefix + colon)
    """

    def test_unquoted_colon_in_title_returns_empty_dict(
        self, tmp_path: Path
    ) -> None:
        note = tmp_path / "bad.md"
        note.write_text(
            "---\n"
            "title: 1-1: Stefan\n"
            "created: 2016-01-01T00:00:00+11:00\n"
            "source: evernote\n"
            "---\n\nbody\n",
            encoding="utf-8",
        )
        assert read_frontmatter(note) == {}

    def test_leading_dash_in_title_returns_empty_dict(
        self, tmp_path: Path
    ) -> None:
        note = tmp_path / "bad.md"
        note.write_text(
            "---\n"
            "title: - Business Card\n"
            "source: evernote\n"
            "---\n\nbody\n",
            encoding="utf-8",
        )
        assert read_frontmatter(note) == {}

    def test_leading_asterisk_in_title_returns_empty_dict(
        self, tmp_path: Path
    ) -> None:
        note = tmp_path / "bad.md"
        note.write_text(
            "---\n"
            "title: * [[APAC 2x2's]]\n"
            "source: evernote\n"
            "---\n\nbody\n",
            encoding="utf-8",
        )
        assert read_frontmatter(note) == {}

    def test_flow_mapping_prefix_with_colon_returns_empty_dict(
        self, tmp_path: Path
    ) -> None:
        note = tmp_path / "bad.md"
        note.write_text(
            "---\n"
            "title: [Cancelled] Credit Card: Skye\n"
            "source: evernote\n"
            "---\n\nbody\n",
            encoding="utf-8",
        )
        assert read_frontmatter(note) == {}

    def test_is_classified_returns_false_for_malformed_yaml(
        self, tmp_path: Path
    ) -> None:
        """Defence-in-depth: is_classified() must not crash either."""
        note = tmp_path / "bad.md"
        note.write_text(
            "---\n"
            "title: 1-1: Stefan\n"
            "---\n\nbody\n",
            encoding="utf-8",
        )
        assert is_classified(note) is False

    def test_valid_yaml_still_parses_after_hardening(
        self, tmp_path: Path
    ) -> None:
        """Regression: hardening must not regress the happy path."""
        note = tmp_path / "good.md"
        note.write_text(
            '---\n'
            'title: "Valid Title"\n'
            'type: meeting\n'
            'org: Amazon\n'
            "---\n\nbody\n",
            encoding="utf-8",
        )
        fm = read_frontmatter(note)
        assert fm["title"] == "Valid Title"
        assert fm["type"] == "meeting"


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


class TestProvisionalProvenance:
    """`classified_by` marks WHO wrote the metadata, so a provisional stamp
    from an external exporter can be upgraded by the LM classifier later.

    Background: granolaSync's export_granola.py hardcodes `context: work` and
    `type: meeting` on every note it writes. Those four required fields being
    present made is_classified() return True, so the LM never revisited them —
    permanently freezing "Bed Linen for the Family" as a work meeting.
    """

    def _fm(self, extra: str = "") -> str:
        return (
            "---\n"
            "type: meeting\n"
            "org: Personal\n"
            "context: work\n"
            'up: "[[Meetings]]"\n'
            f"{extra}"
            "---\n\nbody.\n"
        )

    def test_export_stamped_note_is_not_classified(self, tmp_path: Path) -> None:
        """The whole point: provisional metadata must not block the LM."""
        note = tmp_path / "n.md"
        note.write_text(self._fm("classified_by: export\n"), encoding="utf-8")
        assert is_classified(note) is False

    def test_classifier_stamped_note_is_classified(self, tmp_path: Path) -> None:
        """Once the pipeline has decided, it must not re-process forever."""
        note = tmp_path / "n.md"
        note.write_text(self._fm("classified_by: classifier\n"), encoding="utf-8")
        assert is_classified(note) is True

    def test_legacy_note_without_provenance_stays_classified(
        self, tmp_path: Path
    ) -> None:
        """Backwards compatibility, and it is load-bearing: ~1,483 notes carry
        no provenance. Treating absence as unclassified would queue the entire
        corpus for re-classification — 25+ hours at current LM throughput.
        """
        note = tmp_path / "n.md"
        note.write_text(self._fm(), encoding="utf-8")
        assert is_classified(note) is True

    def test_export_stamp_with_missing_required_field_still_unclassified(
        self, tmp_path: Path
    ) -> None:
        note = tmp_path / "n.md"
        note.write_text(
            '---\ntype: meeting\nclassified_by: export\n---\n\nbody.\n',
            encoding="utf-8",
        )
        assert is_classified(note) is False

    def test_unknown_provenance_value_is_treated_as_classified(
        self, tmp_path: Path
    ) -> None:
        """Only the explicit `export` sentinel reopens a note. An unrecognised
        value must not silently queue notes for re-processing.
        """
        note = tmp_path / "n.md"
        note.write_text(self._fm("classified_by: something-else\n"), encoding="utf-8")
        assert is_classified(note) is True


class TestBlockStyleAlways:
    """Frontmatter must always be block style, never YAML flow style.

    PyYAML's `default_flow_style=None` collapses a mapping with no nested
    collections onto one line: `{date: ..., type: meeting, org: Personal}`.
    Notes carrying `people:`/`tags:` lists escaped this, which is why it went
    unnoticed — but a flat note (every Granola export) got mangled. It stays
    valid YAML and Obsidian still parses it, so nothing breaks loudly; the
    frontmatter just becomes unreadable and un-diffable.
    """

    def test_flat_mapping_is_written_block_style(self, tmp_path: Path) -> None:
        note = tmp_path / "n.md"
        note.write_text("body\n", encoding="utf-8")
        write_frontmatter(
            note,
            {"type": "meeting", "org": "Personal", "context": "work"},
        )
        text = note.read_text(encoding="utf-8")
        assert "{" not in text, f"flow style leaked into frontmatter:\n{text}"
        assert "type: meeting\n" in text
        assert "org: Personal\n" in text

    def test_mapping_with_lists_stays_block_style(self, tmp_path: Path) -> None:
        note = tmp_path / "n.md"
        note.write_text("body\n", encoding="utf-8")
        write_frontmatter(
            note,
            {"type": "meeting", "people": ["Ada L"], "tags": ["x"]},
        )
        text = note.read_text(encoding="utf-8")
        assert "type: meeting\n" in text
        assert "{" not in text.split("---")[1]

    def test_round_trip_preserves_values(self, tmp_path: Path) -> None:
        note = tmp_path / "n.md"
        note.write_text("body\n", encoding="utf-8")
        fields = {"type": "meeting", "org": "Personal", "classified_by": "export"}
        write_frontmatter(note, fields)
        assert read_frontmatter(note) == fields
