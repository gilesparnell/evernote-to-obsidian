"""Unit tests for the control-panel catalogue HTML rendering.

render_catalog() turns the script registry (grouped by priority tier) into
a self-contained dark-theme page with a Run button per runnable script and
a status slot the page polls into.
"""

from __future__ import annotations

from scripts.classify import control_panel as cp
from scripts.classify import script_registry as reg
from scripts.classify.control_panel import render_catalog


class TestRenderCatalog:
    def test_contains_every_script_name(self):
        html = render_catalog()
        for entry in reg.SCRIPTS:
            assert entry["name"] in html, f"{entry['name']} missing from catalog"

    def test_contains_use_case_text(self):
        html = render_catalog()
        for entry in reg.SCRIPTS:
            # Use-case text should be visible so the operator knows when to run it.
            assert entry["use_case"][:20] in html

    def test_run_buttons_carry_registry_key(self):
        html = render_catalog()
        for entry in reg.SCRIPTS:
            if entry["tier"] == "link":
                continue
            # Each runnable card exposes its key for POST /run (never a command).
            assert f'data-key="{entry["key"]}"' in html

    def test_tier_headings_present(self):
        html = render_catalog()
        # Human-friendly tier headings.
        assert "Daily" in html or "daily" in html
        assert "Occasional" in html or "occasional" in html

    def test_done_tier_visually_deemphasised(self):
        # Done-tier cards get a distinguishing class so CSS can dim them.
        html = render_catalog()
        assert "tier-done" in html

    def test_running_job_status_reflected(self):
        # When a job is running for a key, its card shows running state.
        html = render_catalog(job_states={"audit-manifest": {"state": "running"}})
        assert "running" in html.lower()

    def test_is_self_contained_html(self):
        html = render_catalog()
        assert html.lstrip().lower().startswith("<!doctype html")
        assert "<style" in html  # inline CSS, no external stylesheet
        assert html.rstrip().endswith("</html>")

    def test_balanced_article_tags(self):
        # One <article> card per runnable script; opening == closing count.
        html = render_catalog()
        assert html.count("<article") == html.count("</article>")
        assert html.count("<article") >= 1

    def test_shows_version(self):
        # Versioning Discipline: the running version is visible in-app.
        html = render_catalog()
        assert cp.__version__
        assert f"v{cp.__version__}" in html

    def test_brand_names_the_vault(self):
        # The panel runs the whole vault toolkit, not just the classifier.
        html = render_catalog()
        assert "Obsidian Vault Control Panel" in html  # page title
        assert "Obsidian Vault Control" in html  # brand heading

    def test_detail_pane_has_server_controls(self):
        # Server entries need Start / Stop / Open instead of a single Run.
        html = render_catalog()
        assert 'id="d-start"' in html
        assert 'id="d-stop"' in html
        assert 'id="d-open"' in html

    def test_server_row_carries_kind_and_url(self):
        # The review server exposes its kind + url so the JS can wire Start/Open.
        html = render_catalog()
        assert 'data-kind="server"' in html
        assert "http://localhost:8765" in html
