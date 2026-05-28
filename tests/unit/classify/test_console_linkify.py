"""Unit tests for linkify_console_output.

The control panel's console streams raw subprocess output. For a classify run
(with --log-notes) each processed note is logged as a TAB-delimited line:
``<decision>\\t<relpath>[\\t-> <type>]``. linkify_console_output turns the
relpath into an ``obsidian://`` link the operator can click to open the note,
while HTML-escaping everything else so the output can't inject markup.
"""

from __future__ import annotations

from scripts.classify.control_panel import linkify_console_output


class TestLinkifyConsoleOutput:
    def test_note_log_line_becomes_an_obsidian_link(self):
        out = linkify_console_output(
            "auto\tEvernote/notes/x.md\t-> meeting", "Personal"
        )
        assert '<a href="obsidian://open?vault=Personal' in out
        assert "Evernote/notes/x.md</a>" in out  # clickable display text
        assert "meeting" in out  # trailing detail preserved

    def test_plain_text_has_no_links(self):
        out = linkify_console_output(
            "auto_classified=5, needs_review=2, purged=1", "Personal"
        )
        assert "<a " not in out
        assert "auto_classified=5" in out

    def test_html_special_chars_are_escaped(self):
        out = linkify_console_output("<script>alert(1)</script>", "Personal")
        assert "<script>" not in out
        assert "&lt;script&gt;" in out

    def test_path_with_spaces_is_percent_encoded_in_href(self):
        out = linkify_console_output("review\tEvernote/1-1 Dragon.md", "Personal")
        assert "1-1%20Dragon.md" in out  # encoded in the href
        assert "1-1 Dragon.md</a>" in out  # human-readable in the link text
