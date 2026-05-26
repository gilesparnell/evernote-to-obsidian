"""Unit tests for scripts.classify.audio_link_fix.

Yarle's Evernote → Markdown export writes audio attachments as plain
markdown links: `[name.m4a](./_resources/.../name.m4a)`. Obsidian renders
that as a hyperlink, not an inline audio player, and the unescaped spaces
in the relative path frequently break the link resolver entirely.

This module converts those links to Obsidian embed wikilinks: `![[name.m4a]]`.
Obsidian's "Shortest path when possible" setting resolves the basename to
the actual file (audio filenames in this vault are unique — timestamped
exports + ENWatchRecording_* + unknown_filename-<hash>).
"""

from __future__ import annotations

from pathlib import Path

from scripts.classify.audio_link_fix import (
    convert_audio_links,
    process_file,
    process_vault,
)


class TestConvertAudioLinks:
    """Pure text transformation. No I/O."""

    def test_converts_simple_m4a_link_to_embed(self) -> None:
        body = "[Evernote 20150930 19-15-54.m4a](./_resources/Audio.resources/Evernote 20150930 19-15-54.m4a)"
        new_body, count = convert_audio_links(body)
        assert new_body == "![[Evernote 20150930 19-15-54.m4a]]"
        assert count == 1

    def test_converts_mp3_extension(self) -> None:
        body = "[recording.mp3](./_resources/x/recording.mp3)"
        new_body, count = convert_audio_links(body)
        assert new_body == "![[recording.mp3]]"
        assert count == 1

    def test_converts_wav_extension(self) -> None:
        body = "[memo.wav](./_resources/x/memo.wav)"
        new_body, count = convert_audio_links(body)
        assert new_body == "![[memo.wav]]"
        assert count == 1

    def test_converts_uppercase_extension(self) -> None:
        # Defensive: real exports may have inconsistent casing.
        body = "[clip.M4A](./_resources/x/clip.M4A)"
        new_body, count = convert_audio_links(body)
        assert new_body == "![[clip.M4A]]"
        assert count == 1

    def test_uses_basename_from_link_text_not_path(self) -> None:
        # The wikilink should reference the filename portion only, matching
        # Obsidian's "Shortest path when possible" resolver.
        body = "[Evernote 20180510 08-25-09.m4a](./_resources/Note.14.resources/Evernote 20180510 08-25-09.m4a)"
        new_body, _ = convert_audio_links(body)
        assert "![[Evernote 20180510 08-25-09.m4a]]" in new_body
        assert "_resources" not in new_body

    def test_handles_multiple_audio_links_in_one_body(self) -> None:
        body = (
            "[a.m4a](./_r/a.m4a)\n\n"
            "Some prose between\n\n"
            "[b.m4a](./_r/b.m4a)\n"
        )
        new_body, count = convert_audio_links(body)
        assert count == 2
        assert "![[a.m4a]]" in new_body
        assert "![[b.m4a]]" in new_body
        # Prose preserved.
        assert "Some prose between" in new_body

    def test_idempotent_on_already_embedded_audio(self) -> None:
        # Running twice must not double-wrap. `![[a.m4a]]` stays `![[a.m4a]]`.
        body = "![[Evernote 20180510 08-25-09.m4a]]\n\n![[other.m4a]]"
        new_body, count = convert_audio_links(body)
        assert new_body == body
        assert count == 0

    def test_preserves_image_embeds_unchanged(self) -> None:
        # ![alt](path.png) is already an embed — must not be touched.
        body = "![skitch.png](./_resources/x/skitch.png)"
        new_body, count = convert_audio_links(body)
        assert new_body == body
        assert count == 0

    def test_preserves_non_audio_markdown_links(self) -> None:
        # URL links + links to non-audio files must not be touched.
        body = (
            "See [the docs](https://example.com/foo) and "
            "[a pdf](./_r/file.pdf) and "
            "[another note](other-note.md)"
        )
        new_body, count = convert_audio_links(body)
        assert new_body == body
        assert count == 0

    def test_preserves_frontmatter_unchanged(self) -> None:
        # The frontmatter block contains no audio links, but the function
        # operates on the WHOLE text — must leave it intact.
        body = (
            "---\n"
            "title: Test\n"
            "type: clipping\n"
            "---\n\n"
            "[clip.m4a](./_r/clip.m4a)\n"
        )
        new_body, count = convert_audio_links(body)
        assert new_body.startswith("---\ntitle: Test\ntype: clipping\n---\n\n")
        assert "![[clip.m4a]]" in new_body
        assert count == 1

    def test_mixed_audio_and_image_only_converts_audio(self) -> None:
        body = (
            "[audio.m4a](./_r/audio.m4a)\n"
            "![image.png](./_r/image.png)\n"
            "[link](https://example.com)\n"
        )
        new_body, count = convert_audio_links(body)
        assert count == 1
        assert "![[audio.m4a]]" in new_body
        assert "![image.png](./_r/image.png)" in new_body  # image embed preserved
        assert "[link](https://example.com)" in new_body  # external link preserved

    def test_empty_body_returns_unchanged(self) -> None:
        new_body, count = convert_audio_links("")
        assert new_body == ""
        assert count == 0

    def test_audio_link_with_url_encoded_spaces_in_path(self) -> None:
        # Some exports URL-encode spaces in the path. Still an audio link;
        # still must convert. The link-text basename is what matters.
        body = "[Evernote 20150930 19-15-54.m4a](./_r/Audio%20Note.resources/Evernote%2020150930%2019-15-54.m4a)"
        new_body, count = convert_audio_links(body)
        assert count == 1
        assert "![[Evernote 20150930 19-15-54.m4a]]" in new_body


class TestProcessFile:
    """File-level operations: read, convert, atomic write."""

    def test_dry_run_does_not_modify_file(self, tmp_path: Path) -> None:
        f = tmp_path / "note.md"
        original = "[clip.m4a](./_r/clip.m4a)\n"
        f.write_text(original, encoding="utf-8")
        count = process_file(f, dry_run=True)
        assert count == 1  # would convert 1
        assert f.read_text(encoding="utf-8") == original  # unchanged

    def test_real_run_writes_converted_content(self, tmp_path: Path) -> None:
        f = tmp_path / "note.md"
        f.write_text("[clip.m4a](./_r/clip.m4a)\n", encoding="utf-8")
        count = process_file(f, dry_run=False)
        assert count == 1
        assert f.read_text(encoding="utf-8") == "![[clip.m4a]]\n"

    def test_real_run_leaves_no_tmp_file(self, tmp_path: Path) -> None:
        # Atomic write via tmp+rename should clean up.
        f = tmp_path / "note.md"
        f.write_text("[clip.m4a](./_r/clip.m4a)\n", encoding="utf-8")
        process_file(f, dry_run=False)
        leftovers = list(tmp_path.glob("*.tmp"))
        assert leftovers == [], f"Tmp leftover: {leftovers}"

    def test_zero_links_does_not_touch_file(self, tmp_path: Path) -> None:
        # Avoid unnecessary writes when there's nothing to convert —
        # important for iCloud sync churn.
        f = tmp_path / "note.md"
        f.write_text("No audio links here.\n", encoding="utf-8")
        mtime_before = f.stat().st_mtime_ns
        count = process_file(f, dry_run=False)
        assert count == 0
        mtime_after = f.stat().st_mtime_ns
        assert mtime_before == mtime_after, "File touched despite zero conversions"

    def test_idempotent_real_run(self, tmp_path: Path) -> None:
        f = tmp_path / "note.md"
        f.write_text("[clip.m4a](./_r/clip.m4a)\n", encoding="utf-8")
        process_file(f, dry_run=False)
        # Second run finds zero links and leaves the file alone.
        count = process_file(f, dry_run=False)
        assert count == 0


class TestProcessVault:
    """Top-level orchestration: walk, skip-list, summary."""

    def _write(self, p: Path, body: str) -> None:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")

    def test_summary_includes_files_changed_and_links_converted(
        self, tmp_path: Path
    ) -> None:
        self._write(tmp_path / "a.md", "[a.m4a](./_r/a.m4a)\n[b.m4a](./_r/b.m4a)\n")
        self._write(tmp_path / "b.md", "[c.m4a](./_r/c.m4a)\n")
        self._write(tmp_path / "c.md", "no audio here\n")
        summary = process_vault(tmp_path, folder=None, dry_run=False)
        assert summary["files_scanned"] == 3
        assert summary["files_changed"] == 2
        assert summary["links_converted"] == 3

    def test_dry_run_reports_counts_without_writing(self, tmp_path: Path) -> None:
        f = tmp_path / "a.md"
        original = "[a.m4a](./_r/a.m4a)\n"
        self._write(f, original)
        summary = process_vault(tmp_path, folder=None, dry_run=True)
        assert summary["links_converted"] == 1
        assert f.read_text(encoding="utf-8") == original

    def test_skip_list_respects_wiki_directory(self, tmp_path: Path) -> None:
        # wiki/ is operator-curated; never touch it.
        self._write(tmp_path / "wiki" / "x.md", "[x.m4a](./_r/x.m4a)\n")
        self._write(tmp_path / "real.md", "[r.m4a](./_r/r.m4a)\n")
        summary = process_vault(tmp_path, folder=None, dry_run=False)
        assert summary["files_scanned"] == 1
        assert summary["links_converted"] == 1
        # wiki file untouched
        assert (tmp_path / "wiki" / "x.md").read_text(encoding="utf-8") == \
            "[x.m4a](./_r/x.m4a)\n"

    def test_skip_list_respects_personal_backup_prefix(self, tmp_path: Path) -> None:
        self._write(
            tmp_path / "Personal-backup-20260101" / "x.md",
            "[x.m4a](./_r/x.m4a)\n",
        )
        self._write(tmp_path / "real.md", "[r.m4a](./_r/r.m4a)\n")
        summary = process_vault(tmp_path, folder=None, dry_run=False)
        assert summary["files_scanned"] == 1
        assert summary["links_converted"] == 1

    def test_folder_scope_limits_processing(self, tmp_path: Path) -> None:
        self._write(tmp_path / "outside.md", "[o.m4a](./_r/o.m4a)\n")
        self._write(tmp_path / "Job Hunt" / "inside.md", "[i.m4a](./_r/i.m4a)\n")
        summary = process_vault(tmp_path, folder="Job Hunt", dry_run=False)
        assert summary["files_scanned"] == 1
        assert summary["links_converted"] == 1
        # Outside the folder, untouched.
        assert (tmp_path / "outside.md").read_text(encoding="utf-8") == \
            "[o.m4a](./_r/o.m4a)\n"

    def test_empty_vault_returns_zero_counts(self, tmp_path: Path) -> None:
        summary = process_vault(tmp_path, folder=None, dry_run=False)
        assert summary == {
            "files_scanned": 0,
            "files_changed": 0,
            "links_converted": 0,
        }

    def test_hidden_directories_skipped(self, tmp_path: Path) -> None:
        self._write(tmp_path / ".obsidian" / "x.md", "[x.m4a](./_r/x.m4a)\n")
        self._write(tmp_path / "real.md", "[r.m4a](./_r/r.m4a)\n")
        summary = process_vault(tmp_path, folder=None, dry_run=False)
        assert summary["files_scanned"] == 1
