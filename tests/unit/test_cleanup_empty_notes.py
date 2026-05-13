import pytest
from pathlib import Path
from scripts.cleanup_empty_notes import is_empty_note, find_empty_notes, cleanup_empty_notes


# --- is_empty_note ---

def test_empty_note_returns_true(tmp_path):
    f = tmp_path / "empty.md"
    f.write_text("---\ntitle: Empty\ncreated: 2024-01-01\n---\n\n")
    assert is_empty_note(f) is True


def test_note_with_content_returns_false(tmp_path):
    f = tmp_path / "content.md"
    f.write_text("---\ntitle: Has content\n---\n\nSome actual text here.\n")
    assert is_empty_note(f) is False


def test_whitespace_only_body_counts_as_empty(tmp_path):
    f = tmp_path / "ws.md"
    f.write_text("---\ntitle: Whitespace\n---\n\n   \n\t\n")
    assert is_empty_note(f) is True


def test_no_frontmatter_with_content_returns_false(tmp_path):
    f = tmp_path / "nofm.md"
    f.write_text("Just some content with no frontmatter.\n")
    assert is_empty_note(f) is False


def test_no_frontmatter_empty_file_returns_true(tmp_path):
    f = tmp_path / "bare_empty.md"
    f.write_text("")
    assert is_empty_note(f) is True


def test_note_with_only_image_attachment_returns_false(tmp_path):
    f = tmp_path / "img.md"
    f.write_text("---\ntitle: Photo\n---\n\n![[photo.png]]\n")
    assert is_empty_note(f) is False


# --- find_empty_notes ---

def test_find_empty_notes_returns_only_empties(tmp_path):
    (tmp_path / "empty.md").write_text("---\ntitle: Empty\n---\n\n")
    (tmp_path / "full.md").write_text("---\ntitle: Full\n---\n\nContent.\n")
    (tmp_path / "also_empty.md").write_text("---\ntitle: Also\n---\n\n  \n")
    result = find_empty_notes(tmp_path)
    names = {p.name for p in result}
    assert names == {"empty.md", "also_empty.md"}


def test_find_empty_notes_recurses_subdirectories(tmp_path):
    sub = tmp_path / "Notebook A"
    sub.mkdir()
    (sub / "deep_empty.md").write_text("---\ntitle: Deep\n---\n\n")
    (tmp_path / "top.md").write_text("---\ntitle: Top\n---\n\nContent.\n")
    result = find_empty_notes(tmp_path)
    assert len(result) == 1
    assert result[0].name == "deep_empty.md"


def test_find_empty_notes_ignores_non_md_files(tmp_path):
    (tmp_path / "image.png").write_text("")
    (tmp_path / "config.yaml").write_text("")
    result = find_empty_notes(tmp_path)
    assert result == []


def test_find_empty_notes_returns_empty_list_when_none(tmp_path):
    (tmp_path / "note.md").write_text("---\ntitle: Fine\n---\n\nHas content.\n")
    assert find_empty_notes(tmp_path) == []


# --- cleanup_empty_notes ---

def test_dry_run_does_not_delete_files(tmp_path):
    f = tmp_path / "empty.md"
    f.write_text("---\ntitle: Empty\n---\n\n")
    result = cleanup_empty_notes(tmp_path, dry_run=True)
    assert f.exists()
    assert result["deleted"] == 0
    assert result["would_delete"] == 1


def test_live_run_deletes_empty_files(tmp_path):
    f = tmp_path / "empty.md"
    f.write_text("---\ntitle: Empty\n---\n\n")
    result = cleanup_empty_notes(tmp_path, dry_run=False)
    assert not f.exists()
    assert result["deleted"] == 1


def test_live_run_does_not_delete_non_empty_files(tmp_path):
    (tmp_path / "empty.md").write_text("---\ntitle: Empty\n---\n\n")
    keep = tmp_path / "full.md"
    keep.write_text("---\ntitle: Full\n---\n\nContent.\n")
    cleanup_empty_notes(tmp_path, dry_run=False)
    assert keep.exists()


def test_cleanup_returns_correct_counts(tmp_path):
    (tmp_path / "e1.md").write_text("---\ntitle: E1\n---\n\n")
    (tmp_path / "e2.md").write_text("---\ntitle: E2\n---\n\n")
    (tmp_path / "full.md").write_text("---\ntitle: Full\n---\n\nContent.\n")
    result = cleanup_empty_notes(tmp_path, dry_run=False)
    assert result["deleted"] == 2
    assert result["scanned"] == 3
