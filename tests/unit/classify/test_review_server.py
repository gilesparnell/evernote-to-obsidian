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
    resolve_vault_path,
    start_server,
    trash_note,
)


def _write_note(path: Path, body: str = "x") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


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
