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
    parse_review_queue_md,
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


class TestParseReviewQueueMd:
    """parse_review_queue_md reconstructs the queue from a saved
    classification-review.md so the review server can re-render without
    re-running the classifier. The `skip_acted_on` flag prunes rows whose
    underlying file has been deleted or already classified — what the
    triage UI needs after an operator has been making edits in parallel.
    """

    def _write_review_md(self, vault: Path, rows: list[str]) -> Path:
        review = vault / "classification-review.md"
        header = (
            "# Classification Review Queue\n"
            "Generated: 2026-05-15\n\n"
            "| Note | Proposed type | Proposed org | Confidence | Reason |\n"
            "|------|---------------|--------------|------------|--------|\n"
        )
        review.write_text(header + "\n".join(rows) + "\n", encoding="utf-8")
        return review

    def _write_note(
        self, vault: Path, rel: str, frontmatter: str = "", body: str = "x",
    ) -> Path:
        path = vault / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        if frontmatter:
            path.write_text(
                f"---\n{frontmatter}\n---\n\n{body}\n", encoding="utf-8",
            )
        else:
            path.write_text(body + "\n", encoding="utf-8")
        return path

    def test_default_returns_every_row_even_if_file_is_missing(
        self, tmp_path: Path,
    ) -> None:
        # Regression: with no flag, the parser preserves the old behaviour
        # (return every row in the .md, no disc-state filtering).
        review = self._write_review_md(tmp_path, [
            "| [[ghost.md]] | note | Amazon | 0.40 | low |",
        ])
        result = parse_review_queue_md(review)
        assert len(result) == 1
        assert "ghost.md" in str(result[0]["path"])

    def test_skip_acted_on_excludes_missing_files(self, tmp_path: Path) -> None:
        # File listed in the queue has been deleted from disc — the
        # filter prunes it from the rendered queue.
        review = self._write_review_md(tmp_path, [
            "| [[ghost.md]] | note | Amazon | 0.40 | low |",
            "| [[real.md]] | note | Amazon | 0.50 | low |",
        ])
        self._write_note(tmp_path, "real.md")  # only this one exists
        result = parse_review_queue_md(review, skip_acted_on=True)
        assert len(result) == 1
        assert result[0]["path"].name == "real.md"

    def test_skip_acted_on_excludes_already_classified_files(
        self, tmp_path: Path,
    ) -> None:
        # File listed in the queue has been reclassified manually — full
        # R2 frontmatter now on disc, classify_confidence: 1.0. Filter it.
        review = self._write_review_md(tmp_path, [
            "| [[done.md]] | note | Amazon | 0.40 | low |",
            "| [[pending.md]] | note | Amazon | 0.50 | low |",
        ])
        self._write_note(
            tmp_path, "done.md",
            frontmatter=(
                "type: technical\norg: Amazon\ncontext: work\n"
                'up: "[[Technical]]"\nclassify_confidence: 1.0'
            ),
        )
        self._write_note(tmp_path, "pending.md", body="still ambiguous body")
        result = parse_review_queue_md(review, skip_acted_on=True)
        assert len(result) == 1
        assert result[0]["path"].name == "pending.md"

    def test_skip_acted_on_keeps_files_still_needing_review(
        self, tmp_path: Path,
    ) -> None:
        # Happy path: file exists, no R2 frontmatter yet, so the row stays.
        review = self._write_review_md(tmp_path, [
            "| [[pending.md]] | note | Amazon | 0.50 | low |",
        ])
        self._write_note(tmp_path, "pending.md", body="still ambiguous")
        result = parse_review_queue_md(review, skip_acted_on=True)
        assert len(result) == 1
        assert result[0]["path"].name == "pending.md"

    def test_skip_acted_on_empty_file_returns_empty(self, tmp_path: Path) -> None:
        # All queued rows have been acted on — the filtered result is empty.
        review = self._write_review_md(tmp_path, [
            "| [[done.md]] | note | Amazon | 0.40 | low |",
        ])
        self._write_note(
            tmp_path, "done.md",
            frontmatter=(
                "type: note\norg: Amazon\ncontext: work\nup: \"[[Personal]]\""
            ),
        )
        result = parse_review_queue_md(review, skip_acted_on=True)
        assert result == []
