"""Local helper server for the classification review queue.

Serves the rendered review HTML at GET / and exposes two POST endpoints so
the in-browser triage UI can delete or reclassify notes without leaving
the page:

    GET  /health        -> {"ok": True, "vault": "..."}
    GET  /              -> rendered review queue HTML (with buttons)
    POST /delete        -> body {"path": "..."} -> move to ~/.Trash
    POST /reclassify    -> body {"path": "...", "type": "...", "org": "..."}

Bound to 127.0.0.1 only — no listening on external interfaces. Every path
is canonicalised against the configured vault root; anything escaping it
is rejected with HTTP 400. Deletes are recoverable (move to ~/.Trash, not
unlink). Both actions append to per-vault audit logs.

CLI:
    scripts/classify/venv/bin/python -m scripts.classify.review_server \\
        --vault ~/Documents/ObsidianVault/Personal \\
        --port 5050
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import date, datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.classify.classify_vault import UP_MAP, up_for_type  # noqa: E402
from scripts.classify.frontmatter import write_frontmatter  # noqa: E402
from scripts.classify.rules_classifier import ORG_KEYWORDS  # noqa: E402


VALID_TYPES: frozenset[str] = frozenset(UP_MAP.keys())
VALID_ORGS: frozenset[str] = frozenset(ORG_KEYWORDS.keys()) | {"Personal"}
_WORK_ORGS: frozenset[str] = frozenset(ORG_KEYWORDS.keys())  # Amazon, T-Systems, ...

_DELETION_LOG = ".classify_deletions.log"
_RECLASSIFY_LOG = ".classify_reclassifications.log"


class InvalidPath(ValueError):
    """Path provided by the client escapes the vault or is malformed."""


class InvalidReclassification(ValueError):
    """type or org not in the whitelist."""


def resolve_vault_path(vault: Path, relative_or_absolute: str) -> Path:
    """Return a canonical Path that is guaranteed to be inside ``vault``.

    Accepts either a relative path (joined to vault) or an absolute path
    (must already be inside vault). Raises ``InvalidPath`` on anything
    that escapes — caller should turn this into HTTP 400.
    """
    if not relative_or_absolute:
        raise InvalidPath("empty path")

    candidate = Path(relative_or_absolute)
    if not candidate.is_absolute():
        candidate = vault / candidate
    resolved = candidate.resolve()
    vault_resolved = vault.resolve()
    try:
        resolved.relative_to(vault_resolved)
    except ValueError as e:
        raise InvalidPath(f"path escapes vault: {relative_or_absolute}") from e
    return resolved


def _resources_dir_for(note_path: Path) -> Path | None:
    """Locate the paired ``_resources/<basename>.resources/`` folder, if any.

    Evernote substitutes underscores for separators in the resources dir
    name, so ``Foo Bar - Baz.md`` pairs with ``Foo_Bar_-_Baz.resources``.
    We try the substitution rule first, then fall back to listing the
    directory if a single matching folder exists.
    """
    resources_root = note_path.parent / "_resources"
    if not resources_root.is_dir():
        return None
    basename = note_path.stem
    candidate = resources_root / (basename.replace(" ", "_") + ".resources")
    if candidate.is_dir():
        return candidate
    # Fallback: scan for any folder whose name spells the same basename
    # ignoring the underscore-for-space substitution.
    target = basename.replace(" ", "_")
    for d in resources_root.iterdir():
        if d.is_dir() and d.name == f"{target}.resources":
            return d
    return None


def _now_iso() -> str:
    return datetime.now().astimezone().strftime("%Y-%m-%dT%H:%M:%S%z")


def _append_log(vault: Path, filename: str, line: str) -> None:
    log = vault / filename
    with log.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def trash_note(
    vault: Path, note_path: Path, trash_root: Path | None = None,
) -> dict[str, Any]:
    """Move ``note_path`` (and any paired _resources/ folder) into a
    dated subfolder of ``trash_root`` (default: ``~/.Trash``).

    Recoverable: macOS Finder shows files moved to ~/.Trash in the
    Trash UI. Tests pass an alternate trash_root so they don't touch
    the user's actual trash.

    Raises FileNotFoundError if the note doesn't exist.
    """
    if not note_path.exists():
        raise FileNotFoundError(str(note_path))
    if trash_root is None:
        trash_root = Path.home() / ".Trash"

    subfolder = trash_root / f"evernote-cleanup-{date.today():%Y-%m-%d}"
    subfolder.mkdir(parents=True, exist_ok=True)

    md_dest = subfolder / note_path.name
    shutil.move(str(note_path), str(md_dest))

    resources_moved = False
    resources = _resources_dir_for(note_path)
    if resources is not None and resources.exists():
        shutil.move(str(resources), str(subfolder / resources.name))
        resources_moved = True

    rel = note_path.relative_to(vault) if note_path.is_relative_to(vault) else note_path
    _append_log(
        vault, _DELETION_LOG,
        f"{_now_iso()} MOVED {rel}{' +resources' if resources_moved else ''}",
    )

    return {
        "ok": True,
        "moved_to": str(subfolder),
        "resources_moved": resources_moved,
    }


def bulk_trash_notes(
    vault: Path,
    paths: list[str],
    trash_root: Path | None = None,
) -> dict[str, Any]:
    """Trash multiple notes best-effort. Per-path failures (file missing,
    path-escape) are collected as errors; the batch keeps going.

    Returns:
        {
            "ok": bool,           # True iff at least one file moved
            "moved_count": int,
            "moved": [<rel-path>, ...],
            "errors": [{"path": <input>, "error": <msg>}, ...],
        }

    Raises ``ValueError`` if ``paths`` is empty — callers must filter
    out the zero-selection case before hitting this function.
    """
    if not paths:
        raise ValueError("paths must be non-empty")

    moved: list[str] = []
    errors: list[dict[str, str]] = []

    for raw_path in paths:
        try:
            resolved = resolve_vault_path(vault, raw_path)
        except InvalidPath as e:
            errors.append({"path": raw_path, "error": str(e)})
            continue
        try:
            trash_note(vault=vault, note_path=resolved, trash_root=trash_root)
        except FileNotFoundError:
            errors.append({"path": raw_path, "error": "file not found"})
            continue
        moved.append(raw_path)

    return {
        "ok": len(moved) > 0,
        "moved_count": len(moved),
        "moved": moved,
        "errors": errors,
    }


def apply_reclassification(
    vault: Path, note_path: Path, type_: str, org: str,
) -> dict[str, Any]:
    """Write full R2 frontmatter onto ``note_path`` as a manual decision.

    ``context`` is derived from ``org`` (work for known work orgs,
    personal otherwise). ``up`` is derived from ``type_`` via UP_MAP.
    ``classify_confidence`` is set to 1.0 so future runs treat this as
    ground truth and don't re-classify.

    Raises InvalidReclassification on out-of-whitelist values, and
    FileNotFoundError if the note is missing.
    """
    if type_ not in VALID_TYPES:
        raise InvalidReclassification(
            f"type must be one of {sorted(VALID_TYPES)}; got {type_!r}",
        )
    if org not in VALID_ORGS:
        raise InvalidReclassification(
            f"org must be one of {sorted(VALID_ORGS)}; got {org!r}",
        )
    if not note_path.exists():
        raise FileNotFoundError(str(note_path))

    context = "work" if org in _WORK_ORGS else "personal"
    new_fields: dict[str, Any] = {
        "type": type_,
        "org": org,
        "context": context,
        "people": [],
        "tags": [],
        "up": up_for_type(type_),
        "classify_confidence": 1.0,
    }
    write_frontmatter(note_path, new_fields)

    rel = note_path.relative_to(vault) if note_path.is_relative_to(vault) else note_path
    _append_log(
        vault, _RECLASSIFY_LOG,
        f"{_now_iso()} RECLASSIFIED {rel} -> type={type_} org={org}",
    )

    return {"ok": True, "type": type_, "org": org, "context": context}


# ---------------------------------------------------------------------------
# HTTP handler. Thin wrapper over the three helpers above.


class _Handler(BaseHTTPRequestHandler):
    server_version = "EvernoteToObsidianReviewServer/0.2"
    vault: Path  # set on the class by start_server
    trash_root: Path

    def log_message(self, fmt: str, *args: Any) -> None:  # noqa: A003
        # Concise stderr logging — one line per request, no timestamps
        # (the WSGI-style default is noisy).
        sys.stderr.write(f"[review] {fmt % args}\n")

    def _send_json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, status: int, body: str) -> None:
        encoded = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _read_json_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            raise InvalidPath(f"bad JSON: {e}") from e
        if not isinstance(data, dict):
            raise InvalidPath("JSON body must be an object")
        return data

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health":
            self._send_json(200, {"ok": True, "vault": str(self.vault)})
            return
        if self.path == "/" or self.path.startswith("/?"):
            self._send_html(200, _render_review_page(self.vault))
            return
        self._send_json(404, {"ok": False, "error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        try:
            body = self._read_json_body()
        except InvalidPath as e:
            self._send_json(400, {"ok": False, "error": str(e)})
            return

        if self.path == "/delete":
            self._handle_delete(body)
        elif self.path == "/delete-bulk":
            self._handle_delete_bulk(body)
        elif self.path == "/reclassify":
            self._handle_reclassify(body)
        else:
            self._send_json(404, {"ok": False, "error": "not found"})

    def _handle_delete(self, body: dict[str, Any]) -> None:
        path = body.get("path", "")
        try:
            resolved = resolve_vault_path(self.vault, path)
        except InvalidPath as e:
            self._send_json(400, {"ok": False, "error": str(e)})
            return
        try:
            result = trash_note(
                vault=self.vault, note_path=resolved, trash_root=self.trash_root,
            )
        except FileNotFoundError:
            self._send_json(404, {"ok": False, "error": "file not found"})
            return
        self._send_json(200, result)

    def _handle_delete_bulk(self, body: dict[str, Any]) -> None:
        paths = body.get("paths")
        if not isinstance(paths, list) or not all(isinstance(p, str) for p in paths):
            self._send_json(
                400, {"ok": False, "error": "body must be {\"paths\": [str, ...]}"},
            )
            return
        try:
            result = bulk_trash_notes(
                vault=self.vault, paths=paths, trash_root=self.trash_root,
            )
        except ValueError as e:
            # Empty list reached the helper — surface as 400.
            self._send_json(400, {"ok": False, "error": str(e)})
            return
        self._send_json(200, result)

    def _handle_reclassify(self, body: dict[str, Any]) -> None:
        path = body.get("path", "")
        type_ = body.get("type", "")
        org = body.get("org", "")
        try:
            resolved = resolve_vault_path(self.vault, path)
        except InvalidPath as e:
            self._send_json(400, {"ok": False, "error": str(e)})
            return
        try:
            result = apply_reclassification(
                vault=self.vault, note_path=resolved, type_=type_, org=org,
            )
        except InvalidReclassification as e:
            self._send_json(400, {"ok": False, "error": str(e)})
            return
        except FileNotFoundError:
            self._send_json(404, {"ok": False, "error": "file not found"})
            return
        self._send_json(200, result)


def start_server(
    vault: Path,
    trash_root: Path | None = None,
    host: str = "127.0.0.1",
    port: int = 5050,
) -> HTTPServer:
    """Build (but do not run) an HTTPServer instance.

    Caller is responsible for ``serve_forever()`` and ``shutdown()``.
    Tests bind to port 0 (OS picks free port) and read the actual port
    from ``server.server_address[1]``.
    """
    if not vault.is_dir():
        raise ValueError(f"vault is not a directory: {vault}")

    handler_cls = type(
        "_ConfiguredHandler",
        (_Handler,),
        {
            "vault": vault.resolve(),
            "trash_root": (trash_root or Path.home() / ".Trash").resolve(),
        },
    )
    return HTTPServer((host, port), handler_cls)


# ---------------------------------------------------------------------------
# Render the review queue HTML on demand from the vault's
# classification-review.md. Imported here (not from html_renderer) so
# changes to the queue file appear on the next page refresh.


def _render_review_page(vault: Path) -> str:
    from scripts.classify.html_renderer import render_review_queue_html_with_actions
    review_md = vault / "classification-review.md"
    if not review_md.exists():
        return (
            "<!doctype html><html><body style='font-family:sans-serif;padding:2em'>"
            "<h2>No review queue</h2>"
            "<p>No <code>classification-review.md</code> in this vault yet — "
            "run <code>classify_vault.py --html</code> first.</p>"
            "</body></html>"
        )
    return render_review_queue_html_with_actions(vault)


# ---------------------------------------------------------------------------
# CLI


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="review_server",
        description=(
            "Local helper server for triaging the classification review "
            "queue. Serves the rendered HTML at GET / with delete + "
            "reclassify buttons that POST to /delete and /reclassify."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Common patterns:\n\n"
            "  # Triage the chunk-3 review queue\n"
            "  review_server.py --vault ~/Documents/ObsidianVault/Personal\n"
            "  # Open in browser: http://127.0.0.1:5050/\n\n"
            "  # Custom port\n"
            "  review_server.py --vault ~/Documents/ObsidianVault/Personal "
            "--port 8080\n"
        ),
    )
    parser.add_argument("--vault", required=True, type=Path, help="Obsidian vault root.")
    parser.add_argument(
        "--port", type=int, default=5050,
        help="Port to bind on 127.0.0.1 (default 5050).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    server = start_server(vault=args.vault, port=args.port)
    sys.stderr.write(
        f"[review] serving {args.vault} at http://127.0.0.1:{args.port}/\n"
        f"[review] Ctrl-C to stop\n",
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        sys.stderr.write("\n[review] shutting down\n")
    finally:
        server.shutdown()
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
