"""Self-contained HTML renderers for the classifier audit tools.

Produces a single .html file with embedded CSS and no external assets —
safe to open from the file system, share, or commit alongside the .md
audit outputs.

Each note row carries an obsidian://open URL so the operator can click
straight from the browser into the source note in Obsidian.

Public API:
    render_review_queue_html(queue, vault, generated) -> str
    render_sample_html(samples, vault) -> str
"""

from __future__ import annotations

import html
import sys
import urllib.parse
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.classify.frontmatter import read_frontmatter  # noqa: E402

_BODY_EXCERPT_CHARS = 400

_CSS = """
:root {
  --bg: #0a0c10;
  --surface: rgba(255, 255, 255, 0.04);
  --surface-2: rgba(255, 255, 255, 0.07);
  --border: rgba(255, 255, 255, 0.10);
  --text: #e6e8ec;
  --text-dim: #8a8f99;
  --text-faint: #5a5f69;
  --accent: #38bfa0;
  --high: #38bfa0;
  --medium: #f0b429;
  --low: #e5484d;
}
* { box-sizing: border-box; }
html, body {
  margin: 0;
  padding: 0;
  background: var(--bg);
  color: var(--text);
  font-family: -apple-system, BlinkMacSystemFont, "Inter", "Outfit",
               "Helvetica Neue", sans-serif;
  font-size: 14px;
  line-height: 1.5;
}
body {
  max-width: 1100px;
  margin: 0 auto;
  padding: 32px 24px 96px;
}
header {
  border-bottom: 1px solid var(--border);
  padding-bottom: 20px;
  margin-bottom: 28px;
}
h1 {
  font-size: 22px;
  font-weight: 600;
  margin: 0 0 6px;
  letter-spacing: -0.01em;
}
.meta {
  color: var(--text-dim);
  font-size: 12px;
}
.summary {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 14px 18px;
  margin-bottom: 24px;
  color: var(--text-dim);
  font-size: 13px;
}
.card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 16px 18px;
  margin-bottom: 12px;
  transition: background 0.12s ease;
}
.card:hover {
  background: var(--surface-2);
}
.card-head {
  display: flex;
  align-items: baseline;
  gap: 12px;
  margin-bottom: 8px;
}
.card-head a {
  color: var(--accent);
  text-decoration: none;
  font-weight: 600;
  font-size: 14px;
  word-break: break-word;
}
.card-head a:hover { text-decoration: underline; }
.fields {
  color: var(--text-dim);
  font-size: 12px;
  font-family: ui-monospace, SFMono-Regular, "SF Mono", Menlo, monospace;
  margin: 6px 0;
}
.fields span { margin-right: 14px; }
.fields strong { color: var(--text); font-weight: 500; }
.confidence {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 6px;
  font-family: ui-monospace, SFMono-Regular, monospace;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.02em;
}
.confidence-high { background: rgba(56, 191, 160, 0.15); color: var(--high); }
.confidence-medium { background: rgba(240, 180, 41, 0.15); color: var(--medium); }
.confidence-low { background: rgba(229, 72, 77, 0.18); color: var(--low); }
.reason {
  color: var(--text);
  font-size: 13px;
  margin-top: 6px;
}
.reason::before {
  content: "Reason: ";
  color: var(--text-faint);
}
.excerpt {
  background: rgba(0, 0, 0, 0.25);
  border-left: 2px solid var(--border);
  border-radius: 4px;
  padding: 10px 14px;
  margin-top: 10px;
  color: var(--text-dim);
  font-size: 12px;
  white-space: pre-wrap;
  font-family: ui-monospace, SFMono-Regular, monospace;
  max-height: 200px;
  overflow-y: auto;
}
.empty {
  text-align: center;
  padding: 60px 0;
  color: var(--text-faint);
  font-size: 14px;
}
"""

_HTML_SHELL = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{title}</title>
<style>{css}</style>
</head>
<body>
<header>
  <h1>{title}</h1>
  <div class="meta">{meta}</div>
</header>
{body}
</body>
</html>
"""


def _confidence_class(confidence: float) -> str:
    if confidence >= 0.80:
        return "confidence-high"
    if confidence >= 0.50:
        return "confidence-medium"
    return "confidence-low"


def _obsidian_url(vault_name: str, relative_path: Path) -> str:
    """Build an obsidian://open URL for vault+relative path.

    Obsidian's URL scheme percent-encodes the file param; the .md suffix
    is optional but we keep it for explicitness.
    """
    encoded_path = urllib.parse.quote(str(relative_path), safe="")
    encoded_vault = urllib.parse.quote(vault_name, safe="")
    return f"obsidian://open?vault={encoded_vault}&file={encoded_path}"


def _relative_to_vault(path: Path, vault: Path) -> Path:
    try:
        return path.relative_to(vault)
    except ValueError:
        return path


def _strip_frontmatter_body(text: str) -> str:
    import re
    fm = re.match(r"^---\s*\n.*?\n---\s*\n", text, re.DOTALL)
    return text[fm.end():].strip() if fm else text.strip()


def _body_excerpt(path: Path) -> str:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""
    body = _strip_frontmatter_body(text)
    if len(body) > _BODY_EXCERPT_CHARS:
        return body[:_BODY_EXCERPT_CHARS] + "..."
    return body


def render_review_queue_html(
    queue: list[dict[str, Any]], vault: Path, generated: str
) -> str:
    """Render the review queue (low-confidence classifier outputs) as HTML."""
    vault_name = vault.name
    title = "Classification Review Queue"
    meta = (
        f"Generated: {html.escape(generated)} &middot; "
        f"{len(queue)} notes &middot; vault: {html.escape(vault_name)}"
    )

    if not queue:
        body = (
            '<div class="empty">'
            "0 notes need manual review. ✅"
            "</div>"
        )
        return _HTML_SHELL.format(
            title=html.escape(title), css=_CSS, meta=meta, body=body
        )

    cards: list[str] = []
    cards.append(
        f'<div class="summary">{len(queue)} notes need manual review. '
        "Click a note title to open it in Obsidian.</div>"
    )
    for item in queue:
        path: Path = item["path"]
        rel = _relative_to_vault(path, vault)
        url = _obsidian_url(vault_name, rel)
        conf = float(item["confidence"])
        klass = _confidence_class(conf)
        excerpt = _body_excerpt(path)
        cards.append(
            '<article class="card">'
            f'  <div class="card-head">'
            f'    <a href="{html.escape(url, quote=True)}">'
            f'{html.escape(str(rel))}</a>'
            f'    <span class="confidence {klass}">{conf:.2f}</span>'
            f'  </div>'
            f'  <div class="fields">'
            f'    <span><strong>type:</strong> '
            f'{html.escape(str(item.get("proposed_type", "?")))}</span>'
            f'    <span><strong>org:</strong> '
            f'{html.escape(str(item.get("proposed_org", "?")))}</span>'
            f'  </div>'
            f'  <div class="reason">'
            f'{html.escape(str(item.get("reason", "")))}</div>'
            + (
                f'  <pre class="excerpt">{html.escape(excerpt)}</pre>'
                if excerpt else ""
            )
            + '</article>'
        )

    return _HTML_SHELL.format(
        title=html.escape(title), css=_CSS, meta=meta, body="".join(cards)
    )


def render_sample_html(samples: list[Path], vault: Path) -> str:
    """Render a random sample of classified notes as HTML for spot-checking."""
    vault_name = vault.name
    title = "Classification Sample"
    meta = (
        f"{len(samples)} notes &middot; vault: {html.escape(vault_name)}"
    )

    if not samples:
        body = (
            '<div class="empty">'
            "No classified notes matched the filter."
            "</div>"
        )
        return _HTML_SHELL.format(
            title=html.escape(title), css=_CSS, meta=meta, body=body
        )

    cards: list[str] = []
    cards.append(
        '<div class="summary">'
        "Click a note title to open it in Obsidian. The confidence badge "
        "shows the classifier's own self-rated certainty."
        "</div>"
    )
    for path in samples:
        fm = read_frontmatter(path)
        rel = _relative_to_vault(path, vault)
        url = _obsidian_url(vault_name, rel)
        conf = float(fm.get("classify_confidence", 0.0) or 0.0)
        klass = _confidence_class(conf)
        excerpt = _body_excerpt(path)

        # Build the fields strip in a defined order.
        fields_html: list[str] = []
        for label, key in [
            ("type", "type"), ("org", "org"), ("context", "context"),
            ("up", "up"),
        ]:
            value = fm.get(key)
            if value is not None:
                fields_html.append(
                    f'<span><strong>{label}:</strong> '
                    f'{html.escape(str(value))}</span>'
                )
        if fm.get("people"):
            fields_html.append(
                f'<span><strong>people:</strong> '
                f'{html.escape(", ".join(str(p) for p in fm["people"]))}</span>'
            )
        if fm.get("tags"):
            fields_html.append(
                f'<span><strong>tags:</strong> '
                f'{html.escape(", ".join(str(t) for t in fm["tags"]))}</span>'
            )

        cards.append(
            '<article class="card">'
            f'  <div class="card-head">'
            f'    <a href="{html.escape(url, quote=True)}">'
            f'{html.escape(str(rel))}</a>'
            f'    <span class="confidence {klass}">{conf:.2f}</span>'
            f'  </div>'
            f'  <div class="fields">{"".join(fields_html)}</div>'
            + (
                f'  <pre class="excerpt">{html.escape(excerpt)}</pre>'
                if excerpt else ""
            )
            + '</article>'
        )

    return _HTML_SHELL.format(
        title=html.escape(title), css=_CSS, meta=meta, body="".join(cards)
    )
