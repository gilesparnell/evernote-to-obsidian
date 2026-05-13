import sqlite3
import pytest
from scripts.fix_note_links import (
    extract_guid_from_url,
    rewrite_links,
    build_title_to_filename_map,
    build_guid_map,
)

GUID_A = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
GUID_B = "b2c3d4e5-f6a7-8901-bcde-f12345678901"


class TestExtractGuidFromUrl:
    def test_extracts_guid_from_evernote_protocol_url(self):
        url = f"evernote:///view/12345678/s1/{GUID_A}/{GUID_A}/"
        assert extract_guid_from_url(url) == GUID_A.lower()

    def test_extracts_guid_from_evernote_web_url(self):
        url = f"https://www.evernote.com/shard/s1/nl/12345678/{GUID_A}/"
        assert extract_guid_from_url(url) == GUID_A.lower()

    def test_returns_none_for_non_guid_url(self):
        assert extract_guid_from_url("https://example.com/page") is None

    def test_returns_none_for_empty_string(self):
        assert extract_guid_from_url("") is None

    def test_guid_returned_lowercase(self):
        url = f"evernote:///view/12345/s1/{GUID_A.upper()}/{GUID_A.upper()}/"
        assert extract_guid_from_url(url) == GUID_A.lower()

    def test_extracts_guid_from_share_evernote_url(self):
        url = f"https://share.evernote.com/note/{GUID_A}"
        assert extract_guid_from_url(url) == GUID_A.lower()


class TestRewriteLinks:
    def test_rewrites_resolved_evernote_link_to_wikilink(self):
        guid_map = {GUID_A: "My Note"}
        content = f"[See this note](evernote:///view/12345/s1/{GUID_A}/{GUID_A}/)"
        new_content, resolved, unresolved = rewrite_links(content, guid_map)
        # display text differs from filename → alias wikilink
        assert "[[My Note|See this note]]" in new_content
        assert resolved == 1
        assert unresolved == 0

    def test_adds_alias_when_display_text_differs_from_filename(self):
        guid_map = {GUID_A: "meeting-notes-2019"}
        content = f"[see this](evernote:///view/12345/s1/{GUID_A}/{GUID_A}/)"
        new_content, resolved, _ = rewrite_links(content, guid_map)
        assert "[[meeting-notes-2019|see this]]" in new_content
        assert resolved == 1

    def test_no_alias_when_display_text_matches_filename(self):
        guid_map = {GUID_A: "My Note"}
        content = f"[My Note](evernote:///view/1/s1/{GUID_A}/{GUID_A}/)"
        new_content, _, _ = rewrite_links(content, guid_map)
        assert "[[My Note]]" in new_content
        assert "|" not in new_content

    def test_keeps_original_link_when_guid_not_in_map(self):
        guid_map = {}
        original = f"[Missing](evernote:///view/12345/s1/{GUID_A}/{GUID_A}/)"
        new_content, resolved, unresolved = rewrite_links(original, guid_map)
        assert new_content == original
        assert resolved == 0
        assert unresolved == 1

    def test_handles_multiple_links(self):
        guid_map = {GUID_A: "Note A", GUID_B: "Note B"}
        content = (
            f"[Note A](evernote:///view/1/s1/{GUID_A}/{GUID_A}/)\n"
            f"[Note B](evernote:///view/1/s1/{GUID_B}/{GUID_B}/)"
        )
        new_content, resolved, unresolved = rewrite_links(content, guid_map)
        assert "[[Note A]]" in new_content
        assert "[[Note B]]" in new_content
        assert resolved == 2
        assert unresolved == 0

    def test_handles_mixed_resolved_and_unresolved(self):
        guid_map = {GUID_A: "Note A"}
        content = (
            f"[Note A](evernote:///view/1/s1/{GUID_A}/{GUID_A}/) "
            f"[Missing](evernote:///view/1/s1/{GUID_B}/{GUID_B}/)"
        )
        _, resolved, unresolved = rewrite_links(content, guid_map)
        assert resolved == 1
        assert unresolved == 1

    def test_leaves_non_evernote_links_untouched(self):
        content = "[Google](https://google.com)"
        new_content, resolved, unresolved = rewrite_links(content, {GUID_A: "Note A"})
        assert new_content == content
        assert resolved == 0
        assert unresolved == 0

    def test_handles_empty_content(self):
        new_content, resolved, unresolved = rewrite_links("", {})
        assert new_content == ""
        assert resolved == 0
        assert unresolved == 0

    # --- wikilink format: [[evernote://...|text]] ---

    def test_rewrites_wikilink_format_evernote_link(self):
        guid_map = {GUID_A.lower(): "Target Note"}
        content = f"[[evernote:///view/739428/s2/{GUID_A}/{GUID_A}/|Some Display Text]]"
        new_content, resolved, unresolved = rewrite_links(content, guid_map)
        assert new_content == "[[Target Note|Some Display Text]]"
        assert resolved == 1
        assert unresolved == 0

    def test_wikilink_format_drops_alias_when_text_matches_filename(self):
        guid_map = {GUID_A.lower(): "Target Note"}
        content = f"[[evernote:///view/739428/s2/{GUID_A}/{GUID_A}/|Target Note]]"
        new_content, resolved, _ = rewrite_links(content, guid_map)
        assert new_content == "[[Target Note]]"

    def test_wikilink_format_kept_unchanged_when_guid_not_in_map(self):
        content = f"[[evernote:///view/739428/s2/{GUID_A}/{GUID_A}/|Unknown Note]]"
        new_content, resolved, unresolved = rewrite_links(content, {})
        assert new_content == content
        assert resolved == 0
        assert unresolved == 1

    def test_wikilink_format_handles_https_evernote_url(self):
        guid_map = {GUID_A.lower(): "Target Note"}
        content = f"[[https://www.evernote.com/shard/s1/nl/123/{GUID_A}/|Target Note]]"
        new_content, resolved, _ = rewrite_links(content, guid_map)
        assert new_content == "[[Target Note]]"

    def test_rewrites_share_evernote_markdown_link(self):
        guid_map = {GUID_A.lower(): "ATO Note"}
        content = f"[ATO](https://share.evernote.com/note/{GUID_A})"
        new_content, resolved, unresolved = rewrite_links(content, guid_map)
        assert new_content == "[[ATO Note|ATO]]"
        assert resolved == 1
        assert unresolved == 0

    def test_rewrites_share_evernote_no_alias_when_text_matches(self):
        guid_map = {GUID_A.lower(): "ATO Note"}
        content = f"[ATO Note](https://share.evernote.com/note/{GUID_A})"
        new_content, resolved, _ = rewrite_links(content, guid_map)
        assert new_content == "[[ATO Note]]"

    def test_rewrites_share_evernote_wikilink_format(self):
        guid_map = {GUID_A.lower(): "ATO Note"}
        content = f"[[https://share.evernote.com/note/{GUID_A}|ATO]]"
        new_content, resolved, unresolved = rewrite_links(content, guid_map)
        assert new_content == "[[ATO Note|ATO]]"
        assert resolved == 1
        assert unresolved == 0

    def test_both_formats_resolved_in_same_document(self):
        guid_map = {GUID_A.lower(): "Note A", GUID_B.lower(): "Note B"}
        content = (
            f"[Note A](evernote:///view/123/s1/{GUID_A}/{GUID_A}/)\n"
            f"[[evernote:///view/123/s1/{GUID_B}/{GUID_B}/|Note B display]]"
        )
        new_content, resolved, unresolved = rewrite_links(content, guid_map)
        assert "[[Note A]]" in new_content
        assert "[[Note B|Note B display]]" in new_content
        assert resolved == 2
        assert unresolved == 0


class TestBuildTitleToFilenameMap:
    def test_extracts_title_from_frontmatter(self, tmp_path):
        (tmp_path / "my-note.md").write_text(
            "---\ntitle: My Note\ncreated: 2020-01-01\n---\n\nContent."
        )
        result = build_title_to_filename_map(str(tmp_path))
        assert result == {"My Note": "my-note"}

    def test_handles_multiple_files(self, tmp_path):
        (tmp_path / "note-a.md").write_text("---\ntitle: Note A\n---\nContent")
        (tmp_path / "note-b.md").write_text("---\ntitle: Note B\n---\nContent")
        result = build_title_to_filename_map(str(tmp_path))
        assert result["Note A"] == "note-a"
        assert result["Note B"] == "note-b"

    def test_ignores_files_without_frontmatter(self, tmp_path):
        (tmp_path / "no-front.md").write_text("Just plain content, no frontmatter.")
        assert build_title_to_filename_map(str(tmp_path)) == {}

    def test_recurses_into_subdirectories(self, tmp_path):
        sub = tmp_path / "Notebook A"
        sub.mkdir()
        (sub / "nested-note.md").write_text("---\ntitle: Nested Note\n---\nContent")
        result = build_title_to_filename_map(str(tmp_path))
        assert "Nested Note" in result
        assert result["Nested Note"] == "nested-note"

    def test_handles_quoted_title(self, tmp_path):
        (tmp_path / "note.md").write_text('---\ntitle: "Quoted Title"\n---\nContent')
        result = build_title_to_filename_map(str(tmp_path))
        assert "Quoted Title" in result


class TestBuildGuidMap:
    def _make_db(self, tmp_path, rows):
        db_path = str(tmp_path / "test.db")
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE notes (guid TEXT, title TEXT, notebook_guid TEXT)")
        conn.executemany("INSERT INTO notes VALUES (?, ?, ?)", rows)
        conn.commit()
        conn.close()
        return db_path

    def test_maps_guid_to_filename_when_title_matches(self, tmp_path):
        db_path = self._make_db(tmp_path, [(GUID_A, "My Note", "nb1")])
        result = build_guid_map(db_path, {"My Note": "my-note"})
        assert result[GUID_A.lower()] == "my-note"

    def test_excludes_notes_with_no_matching_md_file(self, tmp_path):
        db_path = self._make_db(tmp_path, [(GUID_A, "Unimported Note", "nb1")])
        result = build_guid_map(db_path, {})
        assert result == {}

    def test_guid_key_is_lowercased(self, tmp_path):
        db_path = self._make_db(tmp_path, [(GUID_A.upper(), "My Note", "nb1")])
        result = build_guid_map(db_path, {"My Note": "my-note"})
        assert GUID_A.lower() in result

    def test_handles_multiple_notebooks(self, tmp_path):
        db_path = self._make_db(tmp_path, [
            (GUID_A, "Note A", "nb1"),
            (GUID_B, "Note B", "nb2"),
        ])
        title_map = {"Note A": "note-a", "Note B": "note-b"}
        result = build_guid_map(db_path, title_map)
        assert result[GUID_A.lower()] == "note-a"
        assert result[GUID_B.lower()] == "note-b"

    def test_matches_guid_when_db_title_differs_in_case_from_frontmatter(self, tmp_path):
        # DB: "Partner: Bulletproof"  vs  frontmatter: "Partner: BulletProof"
        db_path = self._make_db(tmp_path, [(GUID_A, "Partner: Bulletproof", "nb1")])
        result = build_guid_map(db_path, {"Partner: BulletProof": "Partner_ BulletProof"})
        assert GUID_A.lower() in result, "case mismatch between DB title and frontmatter should still resolve"
        assert result[GUID_A.lower()] == "Partner_ BulletProof"

    def test_case_insensitive_match_does_not_affect_exact_matches(self, tmp_path):
        # Exact matches should still work after the case-insensitive fix
        db_path = self._make_db(tmp_path, [(GUID_A, "Exact Title", "nb1")])
        result = build_guid_map(db_path, {"Exact Title": "exact-title"})
        assert result[GUID_A.lower()] == "exact-title"

    def test_matches_guid_when_db_title_has_extra_internal_whitespace(self, tmp_path):
        # DB: "My Musings  - Camping in Solitude" (double space)
        # Frontmatter: "My Musings - Camping in Solitude" (single space — Yarle normalises)
        db_path = self._make_db(tmp_path, [(GUID_A, "My Musings  - Camping in Solitude", "nb1")])
        result = build_guid_map(db_path, {"My Musings - Camping in Solitude": "My Musings - Camping in Solitude"})
        assert GUID_A.lower() in result, "double space in DB title should match single-space frontmatter"

    def test_whitespace_and_case_normalisation_together(self, tmp_path):
        # Both case mismatch AND double space at once
        db_path = self._make_db(tmp_path, [(GUID_A, "Doob: Neil Erickson  Project Cape Town Spliff", "nb1")])
        result = build_guid_map(db_path, {"Doob: Neil Erickson Project Cape Town Spliff": "Doob_ Neil Erickson Project Cape Town Spliff"})
        assert GUID_A.lower() in result
