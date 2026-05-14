"""Unit tests for scripts.classify.fix_evernote_titles.

The Evernote .enex → markdown export tool emits YAML frontmatter where the
`title:` value is not quoted, breaking yaml.safe_load when the title
contains structural YAML characters (`:`, leading `-`, leading `*`, etc.).
We found 1,540 such notes in Evernote/notes/AWS on 2026-05-14.

fix_title_yaml() takes the raw note text and returns a corrected version
where the title is wrapped in single quotes (with internal apostrophes
doubled per YAML spec). Returns None if no fix is needed or if the YAML
is broken in a way the title-quoter cannot repair.
"""

from pathlib import Path

import yaml

from scripts.classify.fix_evernote_titles import fix_title_yaml


def _parses(text: str) -> bool:
    import re
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
    if not m:
        return False
    try:
        yaml.safe_load(m.group(1))
        return True
    except yaml.YAMLError:
        return False


class TestFixTitleYAML:
    def test_unquoted_colon_in_title_gets_quoted(self) -> None:
        text = (
            "---\n"
            "title: 1-1: Stefan\n"
            "source: evernote\n"
            "---\n\nbody\n"
        )
        fixed = fix_title_yaml(text)
        assert fixed is not None
        assert "title: '1-1: Stefan'" in fixed
        assert _parses(fixed)

    def test_leading_dash_in_title_gets_quoted(self) -> None:
        text = (
            "---\n"
            "title: - Business Card\n"
            "source: evernote\n"
            "---\n\nbody\n"
        )
        fixed = fix_title_yaml(text)
        assert fixed is not None
        assert "title: '- Business Card'" in fixed
        assert _parses(fixed)

    def test_leading_asterisk_in_title_gets_quoted(self) -> None:
        text = (
            "---\n"
            "title: * [[APAC 2x2 Reports]]\n"
            "source: evernote\n"
            "---\n\nbody\n"
        )
        fixed = fix_title_yaml(text)
        assert fixed is not None
        assert "title: '* [[APAC 2x2 Reports]]'" in fixed
        assert _parses(fixed)

    def test_bracketed_prefix_with_colon_gets_quoted(self) -> None:
        text = (
            "---\n"
            "title: [Cancelled] Credit Card: Skye (Mastercard)\n"
            "source: evernote\n"
            "---\n\nbody\n"
        )
        fixed = fix_title_yaml(text)
        assert fixed is not None
        assert (
            "title: '[Cancelled] Credit Card: Skye (Mastercard)'" in fixed
        )
        assert _parses(fixed)

    def test_apostrophe_in_title_is_escaped_by_doubling(self) -> None:
        text = (
            "---\n"
            "title: 1-1 Elise: DBM SME's\n"
            "source: evernote\n"
            "---\n\nbody\n"
        )
        fixed = fix_title_yaml(text)
        assert fixed is not None
        # YAML single-quote escape is to double the apostrophe.
        assert "title: '1-1 Elise: DBM SME''s'" in fixed
        assert _parses(fixed)
        # Round-trip: the parsed title should equal the original string.
        import re
        m = re.match(r"^---\s*\n(.*?)\n---\s*\n", fixed, re.DOTALL)
        parsed = yaml.safe_load(m.group(1))
        assert parsed["title"] == "1-1 Elise: DBM SME's"

    def test_already_quoted_title_returns_none(self) -> None:
        text = (
            "---\n"
            'title: "Already Quoted"\n'
            "source: evernote\n"
            "---\n\nbody\n"
        )
        assert fix_title_yaml(text) is None

    def test_valid_frontmatter_returns_none(self) -> None:
        text = (
            "---\n"
            "title: Simple\n"
            "type: note\n"
            "---\n\nbody\n"
        )
        # 'Simple' parses fine — no fix needed.
        assert fix_title_yaml(text) is None

    def test_no_frontmatter_returns_none(self) -> None:
        assert fix_title_yaml("Just body, no frontmatter.\n") is None

    def test_other_fields_not_modified(self) -> None:
        text = (
            "---\n"
            "title: 1-1: Stefan\n"
            "created: 2016-01-01T00:00:00+11:00\n"
            "updated: 2016-01-02T00:00:00+11:00\n"
            "source: evernote\n"
            "notebook: AWS\n"
            "---\n\nbody\n"
        )
        fixed = fix_title_yaml(text)
        assert fixed is not None
        for line in (
            "created: 2016-01-01T00:00:00+11:00",
            "updated: 2016-01-02T00:00:00+11:00",
            "source: evernote",
            "notebook: AWS",
        ):
            assert line in fixed

    def test_body_content_preserved(self) -> None:
        body = (
            "\n"
            "# Heading\n\n"
            "Some **markdown** body with - dashes and: colons.\n\n"
            "- list item\n"
        )
        text = "---\ntitle: 1-1: Stefan\n---\n" + body
        fixed = fix_title_yaml(text)
        assert fixed is not None
        assert body in fixed

    def test_unfixable_yaml_returns_none(self) -> None:
        """If quoting the title doesn't make YAML parse, return None
        (rather than write a still-broken file)."""
        text = (
            "---\n"
            "title: ok\n"
            "broken: : : :\n"  # garbage in another field
            "---\n\nbody\n"
        )
        assert fix_title_yaml(text) is None


class TestRealAWSSamplesAreParseable:
    """Regression guard: three known-historically-broken AWS notes must
    parse cleanly. After the 2026-05-14 PM fixer run, the files on disc
    have already been repaired — this test confirms they stay that way.
    """

    SAMPLES = [
        (
            "/Users/gilesparnell/Documents/ObsidianVault/Personal/"
            "Evernote/notes/AWS/- Business Card.md"
        ),
        (
            "/Users/gilesparnell/Documents/ObsidianVault/Personal/"
            "Evernote/notes/AWS/1-1 Conversation_ Discussion Points.md"
        ),
        (
            "/Users/gilesparnell/Documents/ObsidianVault/Personal/"
            "Evernote/notes/AWS/1-1 Elise_ DBM Inbound SME's.md"
        ),
    ]

    def test_each_sample_parses_cleanly(self) -> None:
        for path_str in self.SAMPLES:
            path = Path(path_str)
            if not path.exists():
                continue  # skip if running where the vault isn't mounted
            text = path.read_text(encoding="utf-8")
            assert _parses(text), (
                f"YAML for {path.name} no longer parses — regression."
            )
