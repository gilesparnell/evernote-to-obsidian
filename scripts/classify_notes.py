"""
Note classifier: rules-based scoring + optional Ollama AI pass.

Usage (classify a notebook and launch the review UI):
    python scripts/classify_ui.py --vault ~/ObsidianVault/Evernote --notebook Work

This module is the pure logic layer — no Flask, no side effects.
"""

import re
from pathlib import Path
from typing import Optional

try:
    import ollama
except ImportError:
    ollama = None  # type: ignore

WORK_KEYWORDS: dict[str, float] = {
    "meeting": 3, "agenda": 2, "action items": 3, "standup": 3, "stand-up": 3,
    "sprint": 3, "milestone": 2, "deadline": 2, "deliverable": 3,
    "client": 3, "customer": 2, "vendor": 3, "contract": 3,
    "invoice": 3, "quote": 2, "proposal": 3,
    "budget": 2, "revenue": 3, "quarterly": 3, "kpi": 3, "okr": 3,
    "employee": 2, "onboarding": 3, "performance review": 3, "salary": 2,
    "project": 2, "deployment": 3, "release": 2, "ticket": 2, "jira": 3,
    "stakeholder": 3, "presentation": 2,
    "payroll": 3, "expense": 2, "reimbursement": 3,
    "team": 1, "manager": 2, "ceo": 3, "cto": 3, "cfo": 3,
    "report": 1, "follow up": 1, "follow-up": 1,
}

PERSONAL_KEYWORDS: dict[str, float] = {
    "birthday": 3, "anniversary": 3, "wedding": 3,
    "family": 2, "mum": 3, "dad": 3, "sister": 3, "brother": 3,
    "kids": 3, "children": 2, "school": 2, "homework": 3,
    "recipe": 3, "dinner": 2, "lunch": 1, "breakfast": 2, "cook": 2, "cooking": 2,
    "holiday": 2, "vacation": 3, "travel": 2, "hotel": 2, "flight": 2, "passport": 3,
    "doctor": 3, "dentist": 3, "gym": 3, "health": 2, "medication": 3, "appointment": 2,
    "mortgage": 3, "rent": 2, "insurance": 2,
    "shopping": 2, "wishlist": 3, "gift": 2, "christmas": 3,
    "restaurant": 2, "movie": 2, "hobby": 3,
    "personal": 2, "friend": 2, "weekend": 2, "wife": 3, "husband": 3, "partner": 2,
    "baby": 3, "pregnancy": 3,
}

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_FM_VALUE_RE = re.compile(r"^(\w+):\s*[\"']?(.+?)[\"']?\s*$", re.MULTILINE)


def extract_note_content(md_path: str) -> dict[str, str]:
    """Extract title, notebook, and body from a Yarle-generated .md file."""
    path = Path(md_path)
    text = path.read_text(encoding="utf-8")

    title = path.stem
    notebook = ""
    body = text

    match = _FRONTMATTER_RE.match(text)
    if match:
        fm_block = match.group(1)
        body = text[match.end():]
        for key, value in _FM_VALUE_RE.findall(fm_block):
            if key == "title":
                title = value
            elif key == "notebook":
                notebook = value

    return {"title": title, "notebook": notebook, "body": body.strip()}


def score_note(title: str, body: str) -> tuple[float, float, str]:
    """
    Score a note against work and personal keyword lists.
    Returns (work_score, personal_score, comma-separated matched keywords).
    """
    text = (title + " " + body).lower()
    work_score = 0.0
    personal_score = 0.0
    matched: list[str] = []

    for keyword, weight in WORK_KEYWORDS.items():
        if keyword in text:
            work_score += weight
            matched.append(keyword)

    for keyword, weight in PERSONAL_KEYWORDS.items():
        if keyword in text:
            personal_score += weight
            matched.append(keyword)

    return work_score, personal_score, ", ".join(matched[:6])


def classify_with_rules(title: str, body: str) -> tuple[str, float, str]:
    """
    Rule-based classification.
    Returns (prediction, confidence, reasoning).
    prediction is 'Work', 'Personal', or 'Uncertain'.
    confidence is 0.0–1.0 (0 = no signal, 1 = one-sided).
    """
    work_score, personal_score, keywords = score_note(title, body)
    total = work_score + personal_score

    if total == 0:
        return "Uncertain", 0.0, "no strong signals found"

    work_ratio = work_score / total
    # Map 0.5 (balanced) → 0.0 confidence, 1.0 (one-sided) → 1.0 confidence
    confidence = min(1.0, abs(work_ratio - 0.5) * 2)

    if work_score > personal_score:
        return "Work", confidence, f"work signals: {keywords}"
    else:
        return "Personal", confidence, f"personal signals: {keywords}"


def classify_with_ollama(title: str, body: str, model: str) -> tuple[str, float, str]:
    """
    AI-based classification via Ollama.
    Returns (prediction, confidence, reasoning).
    Raises if Ollama is unavailable or the call fails.
    """
    if ollama is None:
        raise RuntimeError("ollama package not installed — run: pip install ollama")

    prompt = (
        "Classify this note as WORK (professional: meetings, clients, projects, budgets) "
        "or PERSONAL (family, health, hobbies, home, social).\n\n"
        f"Title: {title}\n"
        f"Content: {body[:400]}\n\n"
        "Reply with exactly: WORK or PERSONAL, a dash, then a brief reason (max 10 words).\n"
        'Example: "PERSONAL - birthday party planning for family"'
    )
    response = ollama.chat(model=model, messages=[{"role": "user", "content": prompt}])
    content = response["message"]["content"].strip()
    upper = content.upper()

    if upper.startswith("WORK"):
        reasoning = content[4:].lstrip(" -").strip() or "classified as work"
        return "Work", 0.8, reasoning
    elif upper.startswith("PERSONAL"):
        reasoning = content[8:].lstrip(" -").strip() or "classified as personal"
        return "Personal", 0.8, reasoning
    else:
        return "Uncertain", 0.4, content[:100]


def classify_note(
    md_path: str,
    confidence_threshold: float = 0.7,
    ollama_model: Optional[str] = "llama3.2",
) -> dict:
    """
    Full classification pipeline for a single note.
    Uses rules first; falls back to Ollama for uncertain notes if model is specified.
    """
    note = extract_note_content(md_path)
    title, body = note["title"], note["body"]

    prediction, confidence, reasoning = classify_with_rules(title, body)
    method = "rules"

    if confidence < confidence_threshold and ollama_model and ollama is not None:
        try:
            prediction, confidence, reasoning = classify_with_ollama(title, body, ollama_model)
            method = "ollama"
        except Exception:
            pass  # keep rule-based result on any Ollama failure

    return {
        "path": md_path,
        "title": title,
        "original_notebook": note["notebook"],
        "predicted": prediction,
        "confidence": round(confidence, 3),
        "method": method,
        "reasoning": reasoning,
        "decision": "pending",
    }


def classify_notebook(
    vault_dir: str,
    notebook_name: str,
    confidence_threshold: float = 0.7,
    ollama_model: Optional[str] = "llama3.2",
) -> list[dict]:
    """Classify all .md files in vault_dir/notebook_name/."""
    notebook_dir = Path(vault_dir) / notebook_name
    if not notebook_dir.exists():
        return []
    return [
        classify_note(str(f), confidence_threshold, ollama_model)
        for f in sorted(notebook_dir.glob("*.md"))
    ]


def apply_decisions(decisions: list[dict], vault_dir: str) -> dict:
    """
    Move .md files according to user decisions.
    decision values: 'pending' | 'keep' | 'work' | 'personal'
    Returns stats: moved, skipped, errors.
    """
    stats = {"moved": 0, "skipped": 0, "errors": 0}
    vault = Path(vault_dir)

    notebook_map = {"work": "Work", "personal": "Personal"}

    for dec in decisions:
        decision = dec.get("decision", "pending")

        if decision in ("pending", "keep"):
            stats["skipped"] += 1
            continue

        target_name = notebook_map.get(decision)
        if not target_name:
            stats["skipped"] += 1
            continue

        src = Path(dec["path"])
        current_notebook = src.parent.name

        if current_notebook.lower() == target_name.lower():
            stats["skipped"] += 1
            continue

        target_dir = vault / target_name
        target_dir.mkdir(exist_ok=True)
        target_path = target_dir / src.name

        # Resolve naming conflicts
        if target_path.exists():
            counter = 1
            while target_path.exists():
                target_path = target_dir / f"{src.stem}_{counter}{src.suffix}"
                counter += 1

        try:
            src.rename(target_path)
            stats["moved"] += 1
        except Exception:
            stats["errors"] += 1

    return stats
