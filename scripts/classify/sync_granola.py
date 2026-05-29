"""Pull new Granola meetings, then classify just that folder — in one action.

Two steps the operator otherwise runs by hand:
  1. ``export_granola.py`` (sibling granolaSync repo) pulls new Granola
     meeting notes into ``<vault>/Meetings/``.
  2. ``classify_vault`` classifies the ``Meetings/`` folder. Because the
     classifier skips already-classified notes, only the *new* meetings are
     processed.

If the export step fails (e.g. Granola API/auth error) classification is
skipped — there's nothing new to classify and a half-run shouldn't look like
success.

Usage:
    scripts/classify/venv/bin/python scripts/classify/sync_granola.py \\
        --vault ~/Documents/ObsidianVault/Personal --log-notes
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

# Allow direct script invocation in addition to `python -m`.
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.classify.classify_vault import classify_vault

_GRANOLA_DIR = _REPO_ROOT.parent / "granolaSync"
_SYSTEM_PY = "/opt/homebrew/bin/python3"  # export_granola uses system python
_MEETINGS_FOLDER = "Meetings"  # where export_granola writes (see its docstring)


def _default_export_runner() -> tuple[int, str]:
    """Run ``python3 export_granola.py`` in the granolaSync repo, returning
    (returncode, combined output)."""
    proc = subprocess.run(
        [_SYSTEM_PY, "export_granola.py"],
        cwd=str(_GRANOLA_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    return proc.returncode, proc.stdout


def sync_and_classify(
    vault: Path,
    *,
    folder: str = _MEETINGS_FOLDER,
    dry_run: bool = False,
    log_notes: bool = False,
    export_runner: Callable[[], tuple[int, str]] | None = None,
    classifier: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Pull Granola meetings, then classify ``folder``. ``export_runner`` and
    ``classifier`` are injectable for testing. Returns a summary dict with
    ``status`` ('ok' | 'export_failed'), the export output, and the classify
    summary (None if the pull failed)."""
    export_runner = export_runner or _default_export_runner
    classifier = classifier or classify_vault

    returncode, output = export_runner()
    result: dict[str, Any] = {
        "export_returncode": returncode,
        "export_output": output,
        "classified": None,
    }
    if returncode != 0:
        result["status"] = "export_failed"
        return result

    result["classified"] = classifier(
        vault=vault, folder=folder, dry_run=dry_run, log_notes=log_notes,
    )
    result["status"] = "ok"
    return result


_CLI_DESCRIPTION = """\
Pull new Granola meeting notes (via the granolaSync export) and then classify
the Meetings/ folder in one step. The classifier skips already-classified
notes, so only the newly-pulled meetings are processed. If the Granola export
fails, classification is skipped.
"""


def main() -> None:
    parser = argparse.ArgumentParser(
        description=_CLI_DESCRIPTION,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--vault", required=True, type=Path,
        help="Obsidian vault root (e.g. ~/Documents/ObsidianVault/Personal).",
    )
    parser.add_argument(
        "--folder", default=_MEETINGS_FOLDER,
        help=f"Folder the meetings land in (default: {_MEETINGS_FOLDER}).",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Classify in dry-run mode (no writes) after the pull.",
    )
    parser.add_argument(
        "--log-notes", action="store_true",
        help="Print one line per classified note (clickable in the panel).",
    )
    args = parser.parse_args()

    result = sync_and_classify(
        args.vault, folder=args.folder, dry_run=args.dry_run,
        log_notes=args.log_notes,
    )
    print(f"\ngranola export: rc={result['export_returncode']}")
    if result["status"] == "export_failed":
        print("export failed — classification skipped.")
        sys.exit(1)
    c = result["classified"] or {}
    print(
        f"classified {args.folder}: "
        f"auto_classified={c.get('auto_classified')}, "
        f"needs_review={c.get('needs_review')}"
    )


if __name__ == "__main__":
    main()
