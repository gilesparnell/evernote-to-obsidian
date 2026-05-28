"""Unit tests for scripts.classify.strip_redundant_titles.

Title single-source-of-truth migration (plan 2026-05-28-001). Every note
carried its title in up to three places: filename, frontmatter `title:`,
and (for Granola exports) a leading body `# {title}` H1. This migration
strips the frontmatter `title:` field from all notes, and the leading
body H1 ONLY when it duplicates the title — leaving genuine section
headings intact.

Safe because nothing downstream reads the frontmatter title (the classifier
uses the filename) and no Dataview query references it.
"""

from __future__ import annotations

from pathlib import Path

from scripts.classify.strip_redundant_titles import (
    process_file,
    process_vault,
    strip_matching_body_h1,
    strip_title_frontmatter,
)


# ── strip_title_frontmatter ─────────────────────────────────────────────────


class TestStripTitleFrontmatter:
    def test_removes_title_line_from_frontmatter(self):
        text = (
            "---\n"
            "title: My Note\n"
            "type: meeting\n"
            "org: Amazon\n"
            "---\n\n"
            "Body content.\n"
        )
        new_text, changed = strip_title_frontmatter(text)
        assert changed is True
        assert "title:" not in new_text
        assert "type: meeting" in new_text
        assert "org: Amazon" in new_text
        assert "Body content." in new_text

    def test_removes_quoted_title(self):
        text = (
            "---\n"
            "title: 'Property: Economic Update'\n"
            "type: note\n"
            "---\n\nBody.\n"
        )
        new_text, changed = strip_title_frontmatter(text)
        assert changed is True
        assert "title:" not in new_text
        assert "type: note" in new_text

    def test_no_title_field_returns_unchanged(self):
        text = "---\ntype: note\norg: Personal\n---\n\nBody.\n"
        new_text, changed = strip_title_frontmatter(text)
        assert changed is False
        assert new_text == text

    def test_no_frontmatter_returns_unchanged(self):
        text = "Just body text, no frontmatter.\n"
        new_text, changed = strip_title_frontmatter(text)
        assert changed is False
        assert new_text == text

    def test_only_strips_within_frontmatter_block(self):
        # A line starting "title:" in the BODY must not be touched.
        text = (
            "---\n"
            "type: note\n"
            "---\n\n"
            "title: this is body text not frontmatter\n"
        )
        new_text, changed = strip_title_frontmatter(text)
        assert changed is False
        assert "title: this is body text" in new_text

    def test_preserves_other_frontmatter_order(self):
        text = (
            "---\n"
            "title: X\n"
            "date: 2026-05-20\n"
            "granola_id: abc\n"
            "type: meeting\n"
            "---\n\nB\n"
        )
        new_text, _ = strip_title_frontmatter(text)
        lines = new_text.split("\n")
        # date still precedes granola_id, etc.
        assert lines.index("date: 2026-05-20") < lines.index("granola_id: abc")


# ── strip_matching_body_h1 ──────────────────────────────────────────────────


class TestStripMatchingBodyH1:
    def test_strips_h1_when_it_matches_filename_stem(self):
        text = (
            "---\ntype: meeting\n---\n\n"
            "# Sean- Financial Planning\n\n"
            "**Date:** 2026-05-20\n\nNotes here.\n"
        )
        new_text, changed = strip_matching_body_h1(
            text, "2026-05-20 - Sean- Financial Planning",
        )
        assert changed is True
        assert "# Sean- Financial Planning" not in new_text
        assert "Notes here." in new_text
        assert "**Date:** 2026-05-20" in new_text

    def test_keeps_h1_when_it_does_not_match_title(self):
        # A real section heading that isn't the title — must survive.
        text = (
            "---\ntype: note\n---\n\n"
            "# Property Inspection Feedback\n\n"
            "Weekend inspections went well.\n"
        )
        new_text, changed = strip_matching_body_h1(
            text, "2026-05-25 - RawWhite Property Update",
        )
        assert changed is False
        assert "# Property Inspection Feedback" in new_text

    def test_strips_h1_matching_title_minus_date_prefix(self):
        # The filename stem has a "YYYY-MM-DD - " prefix; the H1 only has
        # the title part. Match against the de-prefixed stem.
        text = "---\ntype: meeting\n---\n\n# My Meeting\n\nbody\n"
        new_text, changed = strip_matching_body_h1(
            text, "2026-05-20 - My Meeting",
        )
        assert changed is True
        assert "# My Meeting" not in new_text

    def test_no_body_h1_returns_unchanged(self):
        # Yarle notes have no body H1 — body starts with content.
        text = "---\ntype: note\n---\n\nJust content, no heading.\n"
        new_text, changed = strip_matching_body_h1(
            text, "2026-05-20 - Some Note",
        )
        assert changed is False
        assert new_text == text

    def test_only_considers_first_heading_not_later_ones(self):
        # A later "# Heading" that happens to match the title should NOT be
        # stripped — only the FIRST body line if it's the title H1.
        text = (
            "---\ntype: meeting\n---\n\n"
            "Some intro line.\n\n"
            "# My Meeting\n\nmore\n"
        )
        new_text, changed = strip_matching_body_h1(text, "2026-05-20 - My Meeting")
        # First body content is prose, not the title H1 → leave everything.
        assert changed is False
        assert "# My Meeting" in new_text


# ── process_file + process_vault ────────────────────────────────────────────


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


class TestProcessFile:
    def test_strips_both_title_and_matching_h1(self, tmp_path):
        p = _write(
            tmp_path / "2026-05-20 - My Meeting.md",
            "---\ntitle: My Meeting\ntype: meeting\n---\n\n"
            "# My Meeting\n\nNotes.\n",
        )
        result = process_file(p, dry_run=False)
        assert result["title_stripped"] is True
        assert result["h1_stripped"] is True
        out = p.read_text(encoding="utf-8")
        assert "title:" not in out
        assert "# My Meeting" not in out
        assert "Notes." in out

    def test_yarle_note_strips_title_only_no_h1(self, tmp_path):
        p = _write(
            tmp_path / "2017-04-01 - Property Update.md",
            "---\ntitle: 'Property: Economic Update'\ntype: note\n---\n\n"
            "Body content with no heading.\n",
        )
        result = process_file(p, dry_run=False)
        assert result["title_stripped"] is True
        assert result["h1_stripped"] is False

    def test_dry_run_does_not_write(self, tmp_path):
        original = "---\ntitle: X\ntype: note\n---\n\n# X\n\nbody\n"
        p = _write(tmp_path / "2026-05-20 - X.md", original)
        result = process_file(p, dry_run=True)
        assert result["title_stripped"] is True
        assert p.read_text(encoding="utf-8") == original  # untouched

    def test_no_changes_does_not_touch_mtime(self, tmp_path):
        p = _write(
            tmp_path / "2026-05-20 - Clean.md",
            "---\ntype: note\n---\n\nNo title, no matching H1.\n",
        )
        before = p.stat().st_mtime_ns
        result = process_file(p, dry_run=False)
        assert result["title_stripped"] is False
        assert result["h1_stripped"] is False
        assert p.stat().st_mtime_ns == before

    def test_idempotent(self, tmp_path):
        p = _write(
            tmp_path / "2026-05-20 - My Meeting.md",
            "---\ntitle: My Meeting\ntype: meeting\n---\n\n# My Meeting\n\nNotes.\n",
        )
        process_file(p, dry_run=False)
        result2 = process_file(p, dry_run=False)
        assert result2 == {"title_stripped": False, "h1_stripped": False}


class TestProcessVault:
    def _write_classified(self, p: Path, title: str) -> Path:
        return _write(
            p,
            f"---\ntitle: {title}\ntype: note\norg: Amazon\n---\n\nbody\n",
        )

    def test_summary_counts_files_and_strips(self, tmp_path):
        self._write_classified(tmp_path / "2026-05-20 - A.md", "A")
        self._write_classified(tmp_path / "2026-05-20 - B.md", "B")
        _write(tmp_path / "2026-05-20 - C.md", "---\ntype: note\n---\n\nclean\n")
        summary = process_vault(tmp_path, folder=None, dry_run=False)
        assert summary["files_scanned"] == 3
        assert summary["titles_stripped"] == 2

    def test_skip_list_respects_wiki(self, tmp_path):
        self._write_classified(tmp_path / "wiki" / "x.md", "X")
        self._write_classified(tmp_path / "real.md", "Real")
        summary = process_vault(tmp_path, folder=None, dry_run=False)
        assert summary["files_scanned"] == 1
        # wiki note untouched
        assert "title: X" in (tmp_path / "wiki" / "x.md").read_text(encoding="utf-8")

    def test_dry_run_writes_nothing(self, tmp_path):
        p = self._write_classified(tmp_path / "2026-05-20 - A.md", "A")
        original = p.read_text(encoding="utf-8")
        process_vault(tmp_path, folder=None, dry_run=True)
        assert p.read_text(encoding="utf-8") == original
