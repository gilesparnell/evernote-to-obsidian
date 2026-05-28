"""Integration tests for the control panel HTTP server.

Boots a real server on an ephemeral 127.0.0.1 port (same pattern as
test_review_server.py) and exercises each endpoint. A test `resolve`
callable is injected so POST /run executes a trivial fast command instead
of a real vault script — the tests never touch the vault or LM Studio.
"""

from __future__ import annotations

import json
import sys
import threading
import time
import urllib.error
import urllib.request

import pytest

from scripts.classify.control_panel import start_server


def _fast_resolve(key: str) -> dict:
    """Test registry: 'fast' prints instantly, 'slow' sleeps, 'srv' is a fake
    long-running server, others unknown."""
    if key == "fast":
        return {"key": "fast", "interpreter": sys.executable, "cwd": ".",
                "argv": ["-c", "print('panel ok')"]}
    if key == "slow":
        return {"key": "slow", "interpreter": sys.executable, "cwd": ".",
                "argv": ["-c", "import time; time.sleep(0.5)"]}
    if key == "srv":
        return {"key": "srv", "interpreter": sys.executable, "cwd": ".",
                "argv": ["-c", "import time; time.sleep(30)"],
                "url": "http://localhost:9999", "kind": "server"}
    if key == "logline":
        return {"key": "logline", "interpreter": sys.executable, "cwd": ".",
                "argv": ["-c", "print('auto\tEvernote/notes/x.md\t-> meeting')"]}
    raise KeyError(key)


@pytest.fixture
def running_server(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    server = start_server(
        host="127.0.0.1", port=0, vault=vault, resolve=_fast_resolve,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.shutdown()
        server.server_close()


def _get(url: str) -> tuple[int, str]:
    try:
        with urllib.request.urlopen(url, timeout=3) as resp:
            return resp.status, resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8")


def _post_json(url: str, body: dict) -> tuple[int, dict | str]:
    req = urllib.request.Request(
        url, data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=3) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8")
        try:
            return e.code, json.loads(raw)
        except json.JSONDecodeError:
            return e.code, raw


class TestHealth:
    def test_health_ok(self, running_server):
        code, body = _get(running_server + "/health")
        assert code == 200
        data = json.loads(body)
        assert data["ok"] is True

    def test_health_reports_version(self, running_server):
        from scripts.classify import control_panel as cp

        code, body = _get(running_server + "/health")
        data = json.loads(body)
        assert data["version"] == cp.__version__
        assert data["version"]


class TestCatalogPage:
    def test_root_serves_catalog_html(self, running_server):
        code, body = _get(running_server + "/")
        assert code == 200
        assert "<!doctype html" in body.lower()
        assert "Obsidian Vault Control Panel" in body
        # Real registry rendered → a known daily tool is present.
        assert "Audit deletions" in body


class TestRunEndpoint:
    def test_run_fast_job_completes(self, running_server):
        code, data = _post_json(running_server + "/run", {"key": "fast"})
        assert code == 200
        job_id = data["job_id"]

        # Poll status to completion.
        deadline = time.monotonic() + 10
        state = "running"
        while time.monotonic() < deadline:
            _, st = _post_json_get_status(running_server, job_id)
            state = st["state"]
            if state != "running":
                break
            time.sleep(0.05)
        assert state == "complete"
        assert "panel ok" in st["output"]

    def test_unknown_key_returns_400_and_does_not_spawn(self, running_server):
        code, data = _post_json(running_server + "/run", {"key": "no-such-key"})
        assert code == 400

    def test_run_while_busy_returns_409(self, running_server):
        # Start a slow job, then immediately try another.
        code1, data1 = _post_json(running_server + "/run", {"key": "slow"})
        assert code1 == 200
        code2, _ = _post_json(running_server + "/run", {"key": "fast"})
        assert code2 == 409
        # Let the slow job drain so the fixture teardown is clean.
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            _, st = _post_json_get_status(running_server, data1["job_id"])
            if st["state"] != "running":
                break
            time.sleep(0.05)

    def test_missing_key_field_returns_400(self, running_server):
        code, _ = _post_json(running_server + "/run", {"not_key": "x"})
        assert code == 400


class TestStatusEndpoint:
    def test_unknown_job_id_returns_404(self, running_server):
        code, _ = _get(running_server + "/status/deadbeef")
        assert code == 404


class TestServerEndpoints:
    def test_start_status_stop_cycle(self, running_server):
        code, body = _post_json(running_server + "/server/start", {"key": "srv"})
        assert code == 200
        assert body["state"] == "running"
        assert body["pid"]
        assert body["url"] == "http://localhost:9999"

        code, raw = _get(running_server + "/server/status/srv")
        assert code == 200
        assert json.loads(raw)["state"] == "running"

        code, body = _post_json(running_server + "/server/stop", {"key": "srv"})
        assert code == 200
        assert body["state"] == "stopped"

    def test_start_unknown_key_returns_400(self, running_server):
        code, _ = _post_json(running_server + "/server/start", {"key": "nope"})
        assert code == 400

    def test_start_non_server_key_returns_400(self, running_server):
        code, _ = _post_json(running_server + "/server/start", {"key": "fast"})
        assert code == 400

    def test_stop_when_not_running_returns_409(self, running_server):
        code, _ = _post_json(running_server + "/server/stop", {"key": "srv"})
        assert code == 409

    def test_status_never_started_reports_stopped_with_url(self, running_server):
        code, raw = _get(running_server + "/server/status/srv")
        assert code == 200
        data = json.loads(raw)
        assert data["state"] == "stopped"
        assert data["url"] == "http://localhost:9999"


class TestConsoleLinks:
    def test_status_output_html_linkifies_note_paths(self, running_server):
        code, data = _post_json(running_server + "/run", {"key": "logline"})
        assert code == 200
        job_id = data["job_id"]
        deadline = time.monotonic() + 10
        st = {}
        while time.monotonic() < deadline:
            _, st = _post_json_get_status(running_server, job_id)
            if st["state"] != "running":
                break
            time.sleep(0.05)
        assert "output_html" in st
        assert "obsidian://open" in st["output_html"]
        assert "<a href=" in st["output_html"]


def _post_json_get_status(base: str, job_id: str) -> tuple[int, dict]:
    code, raw = _get(base + "/status/" + job_id)
    return code, json.loads(raw)
