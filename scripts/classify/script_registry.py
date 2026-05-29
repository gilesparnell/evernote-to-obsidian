"""Allowlist of operator scripts the control panel may run.

This registry is the control panel's security boundary: the panel can only
run entries that appear here, addressed by ``key``. ``POST /run`` accepts a
key, never a command string — so there is no path for arbitrary command
execution.

Each runnable entry is a fixed (interpreter, cwd, argv) triple. Destructive
or long-running scripts get TWO entries — a ``--dry-run`` variant and a real
variant — rather than free-form argument input, which keeps the surface tiny.

Tiers reflect that the bulk migration is now done:
  daily      — the ongoing loop (classify new notes, audit, sample, granola)
  occasional — the next big step (migrate to Business vault)
  done       — one-time migrations, kept runnable for rare new imports
  link       — display-only (a long-running server the panel links to)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

# Repo root = two levels up from this file (scripts/classify/script_registry.py).
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_VENV_PY = _REPO_ROOT / "scripts" / "classify" / "venv" / "bin" / "python"
_GRANOLA_DIR = _REPO_ROOT.parent / "granolaSync"
_SYSTEM_PY = Path("/opt/homebrew/bin/python3")

# Vault paths — pinned config (mirrors how classify_vault.py hardcodes paths).
_PERSONAL_VAULT = Path.home() / "Documents" / "ObsidianVault" / "Personal"
_BUSINESS_VAULT = Path.home() / "Documents" / "ObsidianVault" / "Business"

_TIERS_ORDER = ("daily", "occasional", "done", "link")
_REQUIRED_RUNNABLE = {"key", "name", "use_case", "tier", "interpreter", "cwd", "argv"}
_REQUIRED_LINK = {"key", "name", "use_case", "tier"}
# A server is a long-running process the panel can start/stop; it needs the
# run fields plus a url to open and a kind marker.
_REQUIRED_SERVER = _REQUIRED_RUNNABLE | {"kind", "url"}


SCRIPTS: list[dict[str, Any]] = [
    {
        "key": "classify-dry",
        "name": "Classify vault (dry-run)",
        "use_case": "Preview what a classifier sweep would do to new/unclassified notes — no writes, no deletions.",
        "tier": "daily",
        "interpreter": str(_VENV_PY),
        "cwd": str(_REPO_ROOT),
        "argv": [
            "scripts/classify/classify_vault.py",
            "--vault", str(_PERSONAL_VAULT),
            "--dry-run",
        ],
    },
    {
        "key": "classify-run",
        "name": "Classify vault (apply)",
        "use_case": "Run the classifier on new/unclassified notes — writes frontmatter, purges tiny notes, regenerates the review queue.",
        "tier": "daily",
        "interpreter": str(_VENV_PY),
        "cwd": str(_REPO_ROOT),
        "argv": [
            "scripts/classify/classify_vault.py",
            "--vault", str(_PERSONAL_VAULT),
            "--html",
            "--log-notes",
        ],
    },
    {
        "key": "audit-manifest",
        "name": "Audit deletions",
        "use_case": "Review what the last classifier run hard-deleted — scan for anything you'd want to recover.",
        "tier": "daily",
        "interpreter": str(_VENV_PY),
        "cwd": str(_REPO_ROOT),
        "argv": [
            "scripts/classify/audit_manifest.py",
            "--vault", str(_PERSONAL_VAULT),
        ],
    },
    {
        "key": "dedup-dry",
        "name": "Find duplicate copies (dry-run)",
        "use_case": "Preview the byte-identical 'Title.1.md' copies Yarle left when two Evernote notes shared a title. No changes — counts + lists only.",
        "tier": "daily",
        "interpreter": str(_VENV_PY),
        "cwd": str(_REPO_ROOT),
        "argv": [
            "scripts/classify/dedup_notes.py",
            "--vault", str(_PERSONAL_VAULT),
        ],
    },
    {
        "key": "dedup-run",
        "name": "Remove duplicate copies",
        "use_case": "Delete the byte-identical 'Title.1.md' duplicate copies (the base note is kept). Each is moved to Trash and logged to the deletion manifest.",
        "tier": "daily",
        "interpreter": str(_VENV_PY),
        "cwd": str(_REPO_ROOT),
        "argv": [
            "scripts/classify/dedup_notes.py",
            "--vault", str(_PERSONAL_VAULT),
            "--confirm",
        ],
    },
    {
        "key": "sample",
        "name": "Spot-check classified notes",
        "use_case": "Sample 10 random classified notes to eyeball classification quality.",
        "tier": "daily",
        "interpreter": str(_VENV_PY),
        "cwd": str(_REPO_ROOT),
        "argv": [
            "scripts/classify/sample_classified.py",
            "--vault", str(_PERSONAL_VAULT),
            "--n", "10",
        ],
    },
    {
        "key": "granola",
        "name": "Sync Granola meetings",
        "use_case": "Manually pull the latest Granola meeting notes (normally automatic via the launchd watcher).",
        "tier": "daily",
        "interpreter": str(_SYSTEM_PY),
        "cwd": str(_GRANOLA_DIR),
        "argv": ["export_granola.py"],
    },
    {
        "key": "granola-sync",
        "name": "Sync + classify Granola",
        "use_case": "Pull the latest Granola meetings AND classify just those new notes in one step. The classifier skips already-done notes, so only the new meetings are processed.",
        "tier": "daily",
        "interpreter": str(_VENV_PY),
        "cwd": str(_REPO_ROOT),
        "argv": [
            "scripts/classify/sync_granola.py",
            "--vault", str(_PERSONAL_VAULT),
            "--log-notes",
        ],
    },
    {
        "key": "migrate-dry",
        "name": "Migrate to Business vault (dry-run)",
        "use_case": "Preview splitting work-context notes into the Business vault — counts only, no moves.",
        "tier": "occasional",
        "interpreter": str(_VENV_PY),
        "cwd": str(_REPO_ROOT),
        "argv": [
            "scripts/classify/migrate_vault.py",
            "--personal", str(_PERSONAL_VAULT),
            "--business", str(_BUSINESS_VAULT),
        ],
    },
    {
        "key": "migrate-run",
        "name": "Migrate to Business vault (apply)",
        "use_case": "Move work-context notes to the Business vault. The next big step once classification is complete.",
        "tier": "occasional",
        "interpreter": str(_VENV_PY),
        "cwd": str(_REPO_ROOT),
        "argv": [
            "scripts/classify/migrate_vault.py",
            "--personal", str(_PERSONAL_VAULT),
            "--business", str(_BUSINESS_VAULT),
            "--confirm",
        ],
    },
    {
        "key": "audio-fix",
        "name": "Fix audio links",
        "use_case": "Convert Yarle audio markdown links to playable Obsidian embeds. One-time migration (done) — rerun only after a fresh Evernote import.",
        "tier": "done",
        "interpreter": str(_VENV_PY),
        "cwd": str(_REPO_ROOT),
        "argv": [
            "scripts/classify/audio_link_fix.py",
            "--vault", str(_PERSONAL_VAULT),
        ],
    },
    {
        "key": "strip-titles",
        "name": "Strip redundant titles",
        "use_case": "Remove duplicate title frontmatter + body headings so the filename is the single title. One-time migration (done).",
        "tier": "done",
        "interpreter": str(_VENV_PY),
        "cwd": str(_REPO_ROOT),
        "argv": [
            "scripts/classify/strip_redundant_titles.py",
            "--vault", str(_PERSONAL_VAULT),
        ],
    },
    {
        "key": "review-server",
        "name": "Triage review queue",
        "use_case": "Start the in-browser triage server for the classification review queue, then open it to delete or reclassify notes. Start and Stop it here — it keeps running while you use other tools.",
        "tier": "link",
        "kind": "server",
        "interpreter": str(_VENV_PY),
        "cwd": str(_REPO_ROOT),
        "argv": [
            "scripts/classify/review_server.py",
            "--vault", str(_PERSONAL_VAULT),
            "--port", "8765",
        ],
        "url": "http://localhost:8765",
    },
]


def validate_registry(entries: list[dict[str, Any]]) -> None:
    """Raise ValueError if the registry is malformed: missing required
    fields, duplicate keys, unknown tiers, or runnable entries whose script
    file doesn't exist. Runs at import against SCRIPTS."""
    seen: set[str] = set()
    for e in entries:
        if "key" not in e:
            raise ValueError(f"registry entry missing 'key': {e}")
        key = e["key"]
        if key in seen:
            raise ValueError(f"duplicate registry key: {key}")
        seen.add(key)

        tier = e.get("tier")
        if tier not in _TIERS_ORDER:
            raise ValueError(f"{key}: unknown tier {tier!r}")

        kind = e.get("kind")
        if kind == "server":
            required = _REQUIRED_SERVER
        elif tier == "link":
            required = _REQUIRED_LINK
        else:
            required = _REQUIRED_RUNNABLE
        missing = required - e.keys()
        if missing:
            raise ValueError(f"{key}: missing fields {missing}")

        # Display-only link entries have no script; servers and runnable do.
        if tier == "link" and kind != "server":
            continue

        script = Path(e["cwd"]) / e["argv"][0]
        if not script.exists():
            raise ValueError(f"{key}: script not found at {script}")


def by_tier() -> dict[str, list[dict[str, Any]]]:
    """Return registry entries grouped by tier, tiers in display order
    (daily → occasional → done → link). Empty tiers are omitted."""
    grouped: dict[str, list[dict[str, Any]]] = {}
    for tier in _TIERS_ORDER:
        entries = [e for e in SCRIPTS if e["tier"] == tier]
        if entries:
            grouped[tier] = entries
    return grouped


def get(key: str) -> dict[str, Any]:
    """Resolve a registry key to its entry. Raises KeyError if unknown —
    this is what POST /run uses, so an unknown key never spawns anything."""
    for e in SCRIPTS:
        if e["key"] == key:
            return e
    raise KeyError(key)


# Validate at import — a malformed registry should fail loudly at startup,
# not at request time.
validate_registry(SCRIPTS)
