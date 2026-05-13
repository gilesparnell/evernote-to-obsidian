"""
Note classifier review UI.

Usage:
    python scripts/classify_ui.py --vault ~/ObsidianVault/Evernote --notebook Work

Options:
    --vault      Path to the Evernote vault directory (contains notebook sub-folders)
    --notebook   Name of the notebook to review (e.g. "Work")
    --threshold  Confidence threshold for rule-based pass (default: 0.7)
    --model      Ollama model to use (default: llama3.2). Use "none" to disable AI.
    --port       Local port (default: 5000)
"""

import argparse
import sys
import webbrowser
from pathlib import Path
from threading import Timer

from flask import Flask, jsonify, request

sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.classify_notes import apply_decisions, classify_notebook

app = Flask(__name__)
_state: dict = {"notes": [], "vault_dir": ""}

_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Note Classifier</title>
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
         background: #f0f2f5; color: #1a1a2e; }
  header { background: #1a1a2e; color: white; padding: 14px 24px;
           position: sticky; top: 0; z-index: 10;
           display: flex; justify-content: space-between; align-items: center; }
  header h1 { font-size: 18px; font-weight: 600; }
  #progress { font-size: 13px; color: #aaa; margin-top: 2px; }
  .container { max-width: 820px; margin: 24px auto; padding: 0 16px 100px; }
  .card { background: white; border-radius: 10px; padding: 18px 20px;
          margin-bottom: 14px; box-shadow: 0 1px 3px rgba(0,0,0,.08);
          transition: opacity .2s; }
  .card.done { opacity: .45; }
  .card-title { font-size: 16px; font-weight: 600; margin-bottom: 5px; color: #111; }
  .meta { font-size: 12px; color: #666; margin-bottom: 10px;
          display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
  .tag { display: inline-block; padding: 2px 8px; border-radius: 12px;
         font-size: 11px; font-weight: 600; }
  .tag-work     { background: #fff3cd; color: #856404; }
  .tag-personal { background: #d4edda; color: #155724; }
  .tag-uncertain{ background: #f8d7da; color: #721c24; }
  .conf-high   { background: #d4edda; color: #155724; }
  .conf-medium { background: #fff3cd; color: #856404; }
  .conf-low    { background: #f8d7da; color: #721c24; }
  .excerpt { font-size: 13px; color: #555; background: #f8f9fa; border-radius: 6px;
             padding: 10px 12px; margin-bottom: 10px;
             max-height: 72px; overflow: hidden; line-height: 1.5; }
  .reasoning { font-size: 12px; color: #888; margin-bottom: 12px; }
  .actions { display: flex; gap: 8px; flex-wrap: wrap; }
  .btn { padding: 7px 14px; border: none; border-radius: 6px; cursor: pointer;
         font-size: 13px; font-weight: 500; transition: filter .15s; }
  .btn:hover { filter: brightness(.93); }
  .btn-keep     { background: #e8f0fe; color: #1a73e8; }
  .btn-work     { background: #fff3cd; color: #856404; }
  .btn-personal { background: #d4edda; color: #155724; }
  .decided-msg { font-size: 13px; font-weight: 600; color: #28a745; }
  .empty { text-align: center; padding: 80px 20px; color: #666; }
  .empty h2 { font-size: 22px; margin-bottom: 8px; }
  footer { position: fixed; bottom: 0; left: 0; right: 0; background: #1a1a2e;
           padding: 12px 24px; display: flex; justify-content: space-between; align-items: center; }
  #result { color: #aaa; font-size: 14px; }
  #apply-btn { background: #28a745; color: white; padding: 10px 22px;
               border: none; border-radius: 7px; font-size: 15px; font-weight: 600;
               cursor: pointer; transition: background .15s; }
  #apply-btn:hover:not(:disabled) { background: #218838; }
  #apply-btn:disabled { background: #444; cursor: not-allowed; }
</style>
</head>
<body>
<header>
  <div>
    <h1>Note Classifier Review</h1>
    <div id="progress">Loading…</div>
  </div>
</header>

<div class="container" id="container">
  <div class="empty"><h2>Loading notes…</h2></div>
</div>

<div style="height:70px"></div>
<footer>
  <span id="result"></span>
  <button id="apply-btn" disabled onclick="applyAll()">Apply decisions</button>
</footer>

<script>
let notes = [];

async function load() {
  const r = await fetch('/api/notes');
  notes = await r.json();
  render();
  updateFooter();
}

function esc(s) {
  return String(s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

function confClass(c) {
  return c > 0.7 ? 'conf-high' : c > 0.4 ? 'conf-medium' : 'conf-low';
}

function predClass(p) {
  return p === 'Work' ? 'tag-work' : p === 'Personal' ? 'tag-personal' : 'tag-uncertain';
}

function renderCard(n, i) {
  const pct = Math.round(n.confidence * 100);
  const done = n.decision !== 'pending';
  const decisionLabel = done
    ? `<span class="decided-msg">✓ ${n.decision === 'keep' ? 'Keep here' : 'Move to ' + n.decision.charAt(0).toUpperCase() + n.decision.slice(1)}</span>`
    : `<div class="actions">
        <button class="btn btn-keep" onclick="decide(${i},'keep')">✓ Keep here</button>
        <button class="btn btn-work" onclick="decide(${i},'work')">→ Work</button>
        <button class="btn btn-personal" onclick="decide(${i},'personal')">→ Personal</button>
       </div>`;
  return `
  <div class="card ${done ? 'done' : ''}" id="card-${i}">
    <div class="card-title">${esc(n.title)}</div>
    <div class="meta">
      <span class="tag tag-work">${esc(n.original_notebook)}</span>
      <span style="color:#aaa">→ predicted:</span>
      <span class="tag ${predClass(n.predicted)}">${esc(n.predicted)}</span>
      <span class="tag ${confClass(n.confidence)}">${pct}%</span>
      <span style="color:#bbb;font-size:11px">${esc(n.method)}</span>
    </div>
    <div class="excerpt">${esc(n.excerpt)}</div>
    <div class="reasoning">💡 ${esc(n.reasoning)}</div>
    ${decisionLabel}
  </div>`;
}

function render() {
  const el = document.getElementById('container');
  if (notes.length === 0) {
    el.innerHTML = `<div class="empty">
      <h2>Nothing to review</h2>
      <p>All notes are confidently in the right notebook.</p>
    </div>`;
    return;
  }
  el.innerHTML = notes.map(renderCard).join('');
}

async function decide(i, decision) {
  notes[i].decision = decision;
  document.getElementById(`card-${i}`).outerHTML = renderCard(notes[i], i);
  updateFooter();
  await fetch('/api/decide', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({index: i, decision})
  });
}

function updateFooter() {
  const decided = notes.filter(n => n.decision !== 'pending').length;
  document.getElementById('progress').textContent =
    `${decided} reviewed / ${notes.length} to review`;
  const btn = document.getElementById('apply-btn');
  btn.disabled = decided === 0;
  btn.textContent = decided === 0 ? 'Apply decisions' : `Apply ${decided} decision${decided !== 1 ? 's' : ''}`;
}

async function applyAll() {
  const btn = document.getElementById('apply-btn');
  btn.disabled = true;
  btn.textContent = 'Applying…';
  const r = await fetch('/api/apply', {method:'POST'});
  const s = await r.json();
  document.getElementById('result').textContent =
    `✓ Moved ${s.moved} · Skipped ${s.skipped}${s.errors ? ' · ' + s.errors + ' errors' : ''}`;
  btn.textContent = 'Done';
}

load();
</script>
</body>
</html>"""


def _excerpt(path: str, chars: int = 220) -> str:
    try:
        content = Path(path).read_text(encoding="utf-8")
        if content.startswith("---"):
            end = content.find("---", 3)
            if end > 0:
                content = content[end + 3:]
        return content.strip()[:chars]
    except Exception:
        return ""


@app.route("/")
def index():
    return _HTML


@app.route("/api/notes")
def api_notes():
    return jsonify([{**n, "excerpt": _excerpt(n["path"])} for n in _state["notes"]])


@app.route("/api/decide", methods=["POST"])
def api_decide():
    data = request.get_json()
    _state["notes"][data["index"]]["decision"] = data["decision"]
    return jsonify({"ok": True})


@app.route("/api/apply", methods=["POST"])
def api_apply():
    stats = apply_decisions(_state["notes"], _state["vault_dir"])
    return jsonify(stats)


def main():
    parser = argparse.ArgumentParser(description="Review and reclassify misplaced Evernote notes")
    parser.add_argument("--vault", required=True, help="Path to Evernote vault folder")
    parser.add_argument("--notebook", required=True, help="Notebook name to review (e.g. 'Work')")
    parser.add_argument("--threshold", type=float, default=0.7)
    parser.add_argument("--model", default="llama3.2", help="Ollama model, or 'none' to disable")
    parser.add_argument("--port", type=int, default=5000)
    args = parser.parse_args()

    ollama_model = None if args.model.lower() == "none" else args.model

    print(f"Classifying notes in '{args.notebook}'…")
    all_notes = classify_notebook(args.vault, args.notebook, args.threshold, ollama_model)

    # Show only notes needing review: predicted ≠ original, or uncertain
    review = [n for n in all_notes if n["predicted"] != n["original_notebook"] or n["predicted"] == "Uncertain"]

    print(f"  {len(all_notes)} notes total — {len(review)} need review")

    _state["notes"] = review
    _state["vault_dir"] = args.vault

    url = f"http://localhost:{args.port}"
    Timer(1.0, lambda: webbrowser.open(url)).start()
    print(f"Opening {url}")
    app.run(port=args.port, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
