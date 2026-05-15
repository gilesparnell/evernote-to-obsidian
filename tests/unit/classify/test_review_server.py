"""Unit tests for the review-queue helper server.

Three pure-ish helpers carry the security-critical and side-effect-bearing
logic: path resolution (prevents traversal escape), trash_note (recoverable
delete via ~/.Trash equivalent), and apply_reclassification (writes R2
frontmatter from a manual decision). Tested in isolation; the HTTP layer
is a thin wrapper over these and gets one integration smoke test.
"""

from __future__ import annotations

import json
import threading
import urllib.request
import urllib.error
from pathlib import Path

import pytest

from scripts.classify.frontmatter import read_frontmatter
from scripts.classify.review_server import (
    InvalidPath,
    InvalidReclassification,
    apply_reclassification,
    bulk_trash_notes,
    resolve_vault_path,
    start_server,
    trash_note,
)


def _write_note(path: Path, body: str = "x") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


# ---------------------------------------------------------------------------
# Module-level import surface — the review server should boot fast (it's
# launched manually for ad-hoc triage) and must not transitively pull in
# the LM SDK just to look up a wikilink. Regression: importing classify_vault
# at top-level dragged in openai -> httpx -> 30+ modules, making startup
# slow enough that the operator hit Ctrl-C thinking it was hung.


class TestReviewServerImportSurface:
    def test_importing_review_server_does_not_load_openai_sdk(self) -> None:
        # Spawn a fresh subprocess so cached imports from the test runner
        # don't pollute the check.
        import subprocess
        import sys as _sys
        result = subprocess.run(
            [
                _sys.executable, "-c",
                "import sys\n"
                "from scripts.classify import review_server  # noqa: F401\n"
                "leaks = sorted(\n"
                "    m for m in sys.modules\n"
                "    if m == 'openai' or m.startswith(('openai.', 'httpx', 'httpx.'))\n"
                ")\n"
                "assert not leaks, 'unexpected heavy imports: ' + str(leaks)\n",
            ],
            cwd=str(Path(__file__).resolve().parents[3]),
            capture_output=True,
            text=True,
            timeout=15,
        )
        assert result.returncode == 0, (
            f"review_server import leaked LM SDK transitively:\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )


# ---------------------------------------------------------------------------
# Path resolution — the security gate. Every other helper trusts the path
# coming back from this function to be inside the vault.


class TestResolveVaultPath:
    def test_relative_path_inside_vault_resolves(self, tmp_path: Path) -> None:
        _write_note(tmp_path / "Evernote" / "notes" / "AWS" / "foo.md")
        result = resolve_vault_path(tmp_path, "Evernote/notes/AWS/foo.md")
        assert result == (tmp_path / "Evernote" / "notes" / "AWS" / "foo.md").resolve()

    def test_absolute_path_inside_vault_resolves(self, tmp_path: Path) -> None:
        note = tmp_path / "foo.md"
        _write_note(note)
        result = resolve_vault_path(tmp_path, str(note))
        assert result == note.resolve()

    def test_path_traversal_via_dotdot_blocked(self, tmp_path: Path) -> None:
        with pytest.raises(InvalidPath):
            resolve_vault_path(tmp_path, "../../../etc/passwd")

    def test_absolute_path_outside_vault_blocked(self, tmp_path: Path) -> None:
        with pytest.raises(InvalidPath):
            resolve_vault_path(tmp_path, "/etc/passwd")

    def test_empty_path_rejected(self, tmp_path: Path) -> None:
        with pytest.raises(InvalidPath):
            resolve_vault_path(tmp_path, "")

    def test_path_outside_vault_via_sibling_blocked(self, tmp_path: Path) -> None:
        # Sibling of the vault dir, NOT a child — must be rejected.
        sibling = tmp_path.parent / (tmp_path.name + "-other") / "foo.md"
        with pytest.raises(InvalidPath):
            resolve_vault_path(tmp_path, str(sibling))


# ---------------------------------------------------------------------------
# Trash — recoverable delete. Moves the .md plus any paired _resources/
# folder to a trash root (parametrised so tests don't touch user ~/.Trash).


class TestTrashNote:
    def test_moves_md_file_to_trash_root(self, tmp_path: Path) -> None:
        note = tmp_path / "vault" / "Evernote" / "notes" / "AWS" / "delete-me.md"
        _write_note(note, body="body content")
        trash_root = tmp_path / "trash"

        result = trash_note(
            vault=tmp_path / "vault",
            note_path=note,
            trash_root=trash_root,
        )

        assert result["ok"] is True
        assert not note.exists()
        moved = list(trash_root.rglob("delete-me.md"))
        assert len(moved) == 1
        assert moved[0].read_text(encoding="utf-8") == "body content"

    def test_moves_paired_resources_folder(self, tmp_path: Path) -> None:
        vault = tmp_path / "vault"
        aws = vault / "Evernote" / "notes" / "AWS"
        note = aws / "GoToWebinar Viewer.1.md"
        _write_note(note)
        # Evernote substitutes underscores for separators in resources dir name.
        resources = aws / "_resources" / "GoToWebinar_Viewer.1.resources"
        resources.mkdir(parents=True, exist_ok=True)
        (resources / "image.png").write_bytes(b"PNG")
        trash_root = tmp_path / "trash"

        result = trash_note(
            vault=vault, note_path=note, trash_root=trash_root,
        )

        assert result["ok"] is True
        assert "resources_moved" in result
        assert not note.exists()
        assert not resources.exists()
        # Both note + resources directory landed in the trash subfolder.
        moved_resources = list(trash_root.rglob("GoToWebinar_Viewer.1.resources"))
        assert len(moved_resources) == 1
        assert (moved_resources[0] / "image.png").exists()

    def test_writes_audit_log(self, tmp_path: Path) -> None:
        vault = tmp_path / "vault"
        note = vault / "Evernote" / "notes" / "AWS" / "x.md"
        _write_note(note)
        trash_root = tmp_path / "trash"

        trash_note(vault=vault, note_path=note, trash_root=trash_root)

        log = vault / ".classify_deletions.log"
        assert log.exists()
        content = log.read_text(encoding="utf-8")
        assert "x.md" in content
        # ISO-8601 timestamp on each line (rough check)
        assert "T" in content

    def test_missing_file_raises(self, tmp_path: Path) -> None:
        vault = tmp_path / "vault"
        vault.mkdir()
        trash_root = tmp_path / "trash"
        ghost = vault / "ghost.md"
        with pytest.raises(FileNotFoundError):
            trash_note(vault=vault, note_path=ghost, trash_root=trash_root)


# ---------------------------------------------------------------------------
# Bulk delete — best-effort across a list of paths. Per-path failures (missing
# file, path escape) are collected as errors; the batch continues. Used by the
# multi-select Delete in the triage UI.


class TestBulkTrashNotes:
    def test_moves_all_valid_files_and_returns_summary(self, tmp_path: Path) -> None:
        vault = tmp_path / "vault"
        for name in ("a.md", "b.md", "c.md"):
            _write_note(vault / "Evernote" / "notes" / "AWS" / name, body=name)
        trash_root = tmp_path / "trash"

        result = bulk_trash_notes(
            vault=vault,
            paths=[
                "Evernote/notes/AWS/a.md",
                "Evernote/notes/AWS/b.md",
                "Evernote/notes/AWS/c.md",
            ],
            trash_root=trash_root,
        )

        assert result["ok"] is True
        assert result["moved_count"] == 3
        assert len(result["moved"]) == 3
        assert result["errors"] == []
        # All three are in the trash root
        assert len(list(trash_root.rglob("*.md"))) == 3

    def test_partial_failure_returns_per_path_errors(self, tmp_path: Path) -> None:
        vault = tmp_path / "vault"
        _write_note(vault / "Evernote" / "notes" / "AWS" / "real.md", body="x")
        trash_root = tmp_path / "trash"

        result = bulk_trash_notes(
            vault=vault,
            paths=[
                "Evernote/notes/AWS/real.md",
                "Evernote/notes/AWS/ghost.md",  # never written
            ],
            trash_root=trash_root,
        )

        assert result["ok"] is True  # at least one moved
        assert result["moved_count"] == 1
        assert len(result["moved"]) == 1
        assert len(result["errors"]) == 1
        assert result["errors"][0]["path"] == "Evernote/notes/AWS/ghost.md"
        assert "not found" in result["errors"][0]["error"].lower()

    def test_path_traversal_in_batch_returns_per_path_error(
        self, tmp_path: Path,
    ) -> None:
        vault = tmp_path / "vault"
        _write_note(vault / "real.md")
        trash_root = tmp_path / "trash"

        result = bulk_trash_notes(
            vault=vault,
            paths=["real.md", "../../etc/passwd"],
            trash_root=trash_root,
        )

        assert result["moved_count"] == 1
        assert len(result["errors"]) == 1
        # The escape attempt is reported, the real file still moves.
        assert "escapes vault" in result["errors"][0]["error"]

    def test_empty_list_raises_value_error(self, tmp_path: Path) -> None:
        vault = tmp_path / "vault"
        vault.mkdir()
        with pytest.raises(ValueError):
            bulk_trash_notes(
                vault=vault, paths=[], trash_root=tmp_path / "trash",
            )

    def test_writes_one_audit_line_per_moved_file(self, tmp_path: Path) -> None:
        vault = tmp_path / "vault"
        for name in ("a.md", "b.md"):
            _write_note(vault / name, body=name)
        trash_root = tmp_path / "trash"

        bulk_trash_notes(
            vault=vault,
            paths=["a.md", "b.md"],
            trash_root=trash_root,
        )

        log_lines = (vault / ".classify_deletions.log").read_text(
            encoding="utf-8",
        ).splitlines()
        # Each moved file gets exactly one audit line.
        assert sum(1 for ln in log_lines if "MOVED a.md" in ln) == 1
        assert sum(1 for ln in log_lines if "MOVED b.md" in ln) == 1

    def test_all_failures_returns_ok_false(self, tmp_path: Path) -> None:
        vault = tmp_path / "vault"
        vault.mkdir()
        trash_root = tmp_path / "trash"

        result = bulk_trash_notes(
            vault=vault,
            paths=["ghost1.md", "ghost2.md"],
            trash_root=trash_root,
        )

        # Nothing was moved — top-level ok flips to False.
        assert result["ok"] is False
        assert result["moved_count"] == 0
        assert len(result["errors"]) == 2


# ---------------------------------------------------------------------------
# Reclassification — manual decision applied as R2 frontmatter, confidence
# 1.0 so it's never re-classified by a future chunk.


class TestApplyReclassification:
    def test_writes_full_r2_frontmatter(self, tmp_path: Path) -> None:
        note = tmp_path / "vault" / "Evernote" / "notes" / "AWS" / "x.md"
        _write_note(note, body="some body content")
        vault = tmp_path / "vault"

        result = apply_reclassification(
            vault=vault, note_path=note, type_="technical", org="Amazon",
        )

        assert result["ok"] is True
        fm = read_frontmatter(note)
        assert fm["type"] == "technical"
        assert fm["org"] == "Amazon"
        assert fm["context"] == "work"
        assert fm["up"] == "[[Technical]]"
        assert fm["classify_confidence"] == 1.0
        # body preserved
        assert "some body content" in note.read_text(encoding="utf-8")

    def test_derives_personal_context_for_personal_org(self, tmp_path: Path) -> None:
        note = tmp_path / "vault" / "x.md"
        _write_note(note)
        result = apply_reclassification(
            vault=tmp_path / "vault", note_path=note,
            type_="recipe", org="Personal",
        )
        assert result["ok"] is True
        fm = read_frontmatter(note)
        assert fm["context"] == "personal"
        assert fm["up"] == "[[Personal]]"

    def test_invalid_type_rejected(self, tmp_path: Path) -> None:
        note = tmp_path / "vault" / "x.md"
        _write_note(note)
        with pytest.raises(InvalidReclassification):
            apply_reclassification(
                vault=tmp_path / "vault", note_path=note,
                type_="bogus_type", org="Amazon",
            )

    def test_invalid_org_rejected(self, tmp_path: Path) -> None:
        note = tmp_path / "vault" / "x.md"
        _write_note(note)
        with pytest.raises(InvalidReclassification):
            apply_reclassification(
                vault=tmp_path / "vault", note_path=note,
                type_="technical", org="<script>",
            )

    def test_writes_audit_log(self, tmp_path: Path) -> None:
        note = tmp_path / "vault" / "x.md"
        _write_note(note)
        vault = tmp_path / "vault"
        apply_reclassification(
            vault=vault, note_path=note, type_="technical", org="Amazon",
        )
        log = vault / ".classify_reclassifications.log"
        assert log.exists()
        content = log.read_text(encoding="utf-8")
        assert "x.md" in content
        assert "technical" in content
        assert "Amazon" in content


# ---------------------------------------------------------------------------
# HTTP integration — one smoke test per endpoint, against a real server on
# an ephemeral port. Confirms the wrapping handler reads JSON, routes, and
# returns the dicts from the pure helpers.


@pytest.fixture
def running_server(tmp_path: Path):
    vault = tmp_path / "vault"
    vault.mkdir()
    note = vault / "Evernote" / "notes" / "AWS" / "delete-me.md"
    _write_note(note, body="ephemeral")
    trash_root = tmp_path / "trash"

    server = start_server(
        vault=vault,
        trash_root=trash_root,
        host="127.0.0.1",
        port=0,  # let OS pick a free port
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]
    try:
        yield {"base": f"http://127.0.0.1:{port}", "vault": vault, "trash": trash_root, "note": note}
    finally:
        server.shutdown()
        server.server_close()


def _post_json(url: str, body: dict) -> tuple[int, dict]:
    req = urllib.request.Request(
        url, data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=3) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


class TestHttpEndpoints:
    def test_health_endpoint(self, running_server) -> None:
        with urllib.request.urlopen(running_server["base"] + "/health", timeout=3) as resp:
            data = json.loads(resp.read())
        assert data["ok"] is True
        assert "vault" in data

    def test_delete_endpoint_moves_file(self, running_server) -> None:
        code, data = _post_json(
            running_server["base"] + "/delete",
            {"path": "Evernote/notes/AWS/delete-me.md"},
        )
        assert code == 200
        assert data["ok"] is True
        assert not running_server["note"].exists()

    def test_delete_endpoint_rejects_path_traversal(self, running_server) -> None:
        code, data = _post_json(
            running_server["base"] + "/delete",
            {"path": "../../etc/passwd"},
        )
        assert code == 400
        assert data["ok"] is False

    def test_reclassify_endpoint_writes_frontmatter(self, running_server) -> None:
        code, data = _post_json(
            running_server["base"] + "/reclassify",
            {
                "path": "Evernote/notes/AWS/delete-me.md",
                "type": "technical",
                "org": "Amazon",
            },
        )
        assert code == 200
        assert data["ok"] is True
        fm = read_frontmatter(running_server["note"])
        assert fm["type"] == "technical"
        assert fm["org"] == "Amazon"

    def test_reclassify_endpoint_rejects_invalid_type(self, running_server) -> None:
        code, data = _post_json(
            running_server["base"] + "/reclassify",
            {
                "path": "Evernote/notes/AWS/delete-me.md",
                "type": "bogus",
                "org": "Amazon",
            },
        )
        assert code == 400
        assert data["ok"] is False

    def test_delete_bulk_endpoint_moves_multiple_files(self, running_server) -> None:
        # Write a couple more notes alongside the fixture's delete-me.md
        vault: Path = running_server["vault"]
        for name in ("b.md", "c.md"):
            _write_note(vault / "Evernote" / "notes" / "AWS" / name, body=name)

        code, data = _post_json(
            running_server["base"] + "/delete-bulk",
            {"paths": [
                "Evernote/notes/AWS/delete-me.md",
                "Evernote/notes/AWS/b.md",
                "Evernote/notes/AWS/c.md",
            ]},
        )
        assert code == 200
        assert data["ok"] is True
        assert data["moved_count"] == 3
        assert not running_server["note"].exists()
        assert not (vault / "Evernote" / "notes" / "AWS" / "b.md").exists()

    def test_delete_bulk_endpoint_partial_failure_returns_per_path_status(
        self, running_server,
    ) -> None:
        code, data = _post_json(
            running_server["base"] + "/delete-bulk",
            {"paths": [
                "Evernote/notes/AWS/delete-me.md",
                "Evernote/notes/AWS/ghost-never-existed.md",
            ]},
        )
        assert code == 200
        assert data["moved_count"] == 1
        assert len(data["errors"]) == 1
        assert (
            data["errors"][0]["path"]
            == "Evernote/notes/AWS/ghost-never-existed.md"
        )

    def test_delete_bulk_endpoint_empty_list_returns_400(self, running_server) -> None:
        code, data = _post_json(
            running_server["base"] + "/delete-bulk",
            {"paths": []},
        )
        assert code == 400
        assert data["ok"] is False

    def test_root_renders_review_page_with_multiselect_toolbar(
        self, running_server,
    ) -> None:
        # Seed a minimal review.md so the renderer has something to show.
        review = running_server["vault"] / "classification-review.md"
        review.write_text(
            "# Classification Review Queue\n"
            "Generated: 2026-05-15\n\n"
            "| Note | Proposed type | Proposed org | Confidence | Reason |\n"
            "|------|---------------|--------------|------------|--------|\n"
            "| [[Evernote/notes/AWS/delete-me.md]] | note | Amazon | 0.40 |"
            " low confidence |\n",
            encoding="utf-8",
        )
        with urllib.request.urlopen(running_server["base"] + "/", timeout=3) as resp:
            html_body = resp.read().decode("utf-8")
        # Multi-select toolbar + per-card checkbox + bulk handler all present.
        assert "selection-toolbar" in html_body
        assert 'class="select-checkbox"' in html_body
        assert "doDeleteSelected" in html_body
        assert "delete-bulk" in html_body
