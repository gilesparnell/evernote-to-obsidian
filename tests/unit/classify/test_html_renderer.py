"""Unit tests for scripts.classify.html_renderer.

The HTML renderer produces self-contained HTML (embedded CSS, no external
assets) for two consumers:

  1. classify_vault.py's review queue — low-confidence calls to triage
  2. sample_classified.py's random samples — spot-check of confident calls

Both output formats include obsidian://open URLs so the user can click
from the browser straight into the note in Obsidian.
"""

from pathlib import Path

from scripts.classify.html_renderer import (
    render_review_queue_html,
    render_sample_html,
)


class TestRenderReviewQueueHTML:
    def test_empty_queue_renders_clean_state(self) -> None:
        html = render_review_queue_html(
            queue=[], vault=Path("/tmp/Personal"), generated="2026-05-14"
        )
        assert "<html" in html
        assert "0 notes" in html or "No notes" in html

    def test_single_item_renders_all_fields(self) -> None:
        html = render_review_queue_html(
            queue=[{
                "path": Path("/tmp/Personal/Evernote/notes/AWS/Sample.md"),
                "proposed_type": "technical",
                "proposed_org": "Amazon",
                "confidence": 0.65,
                "reason": "mixed signals",
            }],
            vault=Path("/tmp/Personal"),
            generated="2026-05-14",
        )
        assert "Sample.md" in html
        assert "technical" in html
        assert "Amazon" in html
        assert "0.65" in html
        assert "mixed signals" in html

    def test_confidence_buckets_high_medium_low(self) -> None:
        """Confidence visualisation should bucket the value for at-a-glance
        triage. Green/amber/red mapping is enforced by CSS class names."""
        queue = [
            {
                "path": Path("/tmp/Personal/a.md"), "proposed_type": "note",
                "proposed_org": "?", "confidence": 0.95, "reason": "x",
            },
            {
                "path": Path("/tmp/Personal/b.md"), "proposed_type": "note",
                "proposed_org": "?", "confidence": 0.55, "reason": "x",
            },
            {
                "path": Path("/tmp/Personal/c.md"), "proposed_type": "note",
                "proposed_org": "?", "confidence": 0.10, "reason": "x",
            },
        ]
        html = render_review_queue_html(
            queue=queue, vault=Path("/tmp/Personal"), generated="2026-05-14"
        )
        # The renderer assigns a CSS class per bucket.
        assert "confidence-high" in html  # 0.95
        assert "confidence-medium" in html  # 0.55
        assert "confidence-low" in html  # 0.10

    def test_obsidian_url_uses_vault_name_and_relative_path(self) -> None:
        html = render_review_queue_html(
            queue=[{
                "path": Path(
                    "/tmp/Personal/Evernote/notes/AWS/Some Note.md"
                ),
                "proposed_type": "note",
                "proposed_org": "?",
                "confidence": 0.5,
                "reason": "x",
            }],
            vault=Path("/tmp/Personal"),
            generated="2026-05-14",
        )
        # Vault name should be the leaf of the vault path.
        assert "vault=Personal" in html
        # Path should be URL-escaped (space → %20).
        assert (
            "file=Evernote%2Fnotes%2FAWS%2FSome%20Note" in html
            or "file=Evernote%2Fnotes%2FAWS%2FSome%20Note.md" in html
        )

    def test_html_escapes_special_chars_in_path(self) -> None:
        """A note titled <script> shouldn't break the rendered HTML."""
        html = render_review_queue_html(
            queue=[{
                "path": Path("/tmp/Personal/<dangerous>.md"),
                "proposed_type": "note",
                "proposed_org": "?",
                "confidence": 0.5,
                "reason": "x",
            }],
            vault=Path("/tmp/Personal"),
            generated="2026-05-14",
        )
        assert "<script>" not in html
        assert "&lt;dangerous&gt;" in html

    def test_html_escapes_reason_with_html_chars(self) -> None:
        html = render_review_queue_html(
            queue=[{
                "path": Path("/tmp/Personal/a.md"),
                "proposed_type": "note",
                "proposed_org": "?",
                "confidence": 0.5,
                "reason": "contains <em>html</em>",
            }],
            vault=Path("/tmp/Personal"),
            generated="2026-05-14",
        )
        assert "<em>html</em>" not in html
        assert "&lt;em&gt;html&lt;/em&gt;" in html

    def test_generated_timestamp_is_present(self) -> None:
        html = render_review_queue_html(
            queue=[],
            vault=Path("/tmp/Personal"),
            generated="2026-05-14T11:59:20+10:00",
        )
        assert "2026-05-14T11:59:20+10:00" in html


class TestRenderSampleHTML:
    def _make_note(self, dir: Path, name: str, fm: str, body: str) -> Path:
        note = dir / name
        note.write_text(f"---\n{fm}---\n\n{body}\n", encoding="utf-8")
        return note

    def test_empty_samples_renders_no_results(self, tmp_path: Path) -> None:
        html = render_sample_html(samples=[], vault=tmp_path)
        assert "<html" in html
        assert "No" in html  # "No classified notes" or similar

    def test_includes_frontmatter_fields(self, tmp_path: Path) -> None:
        note = self._make_note(
            tmp_path,
            "sample.md",
            (
                "type: technical\n"
                "org: Amazon\n"
                "context: work\n"
                'up: "[[Technical]]"\n'
                "people: [Alice, Bob]\n"
                "tags: [aws, ec2]\n"
                "classify_confidence: 0.92\n"
            ),
            "Body content goes here.",
        )
        html = render_sample_html(samples=[note], vault=tmp_path)
        assert "technical" in html
        assert "Amazon" in html
        assert "0.92" in html
        assert "Alice" in html
        assert "aws" in html

    def test_body_excerpt_present(self, tmp_path: Path) -> None:
        note = self._make_note(
            tmp_path, "sample.md", "type: note\norg: x\n",
            "This is the body content I want to see in the HTML."
        )
        html = render_sample_html(samples=[note], vault=tmp_path)
        assert "body content I want to see" in html

    def test_html_escapes_body_with_html_chars(self, tmp_path: Path) -> None:
        note = self._make_note(
            tmp_path, "sample.md", "type: note\norg: x\n",
            "Dangerous body: <script>alert('xss')</script>"
        )
        html = render_sample_html(samples=[note], vault=tmp_path)
        assert "<script>alert" not in html
        assert "&lt;script&gt;" in html

    def test_obsidian_url_uses_vault_leaf_name(self, tmp_path: Path) -> None:
        # vault path leaf is the name tmp_path generates (some pytest-XXXXX)
        # — what matters is that the URL contains vault=<leaf>
        note = self._make_note(
            tmp_path, "sample.md", "type: note\norg: x\n", "body"
        )
        html = render_sample_html(samples=[note], vault=tmp_path)
        assert f"vault={tmp_path.name}" in html
