"""Invariant tests for the double-clickable control-panel launcher.

`obsidian-vault-control-panel.command` is a thin shell launcher (Finder double-click) that
starts control_panel.py and opens the browser. These tests guard the wiring
that would silently rot: the launcher must point at the venv python, the real
script, and — critically — the SAME port the panel defaults to, so the URL it
opens can never drift away from the port the server binds.
"""

from __future__ import annotations

import os
from pathlib import Path

from scripts.classify import control_panel as cp

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_LAUNCHER = _REPO_ROOT / "obsidian-vault-control-panel.command"


class TestControlPanelLauncher:
    def test_launcher_exists(self):
        assert _LAUNCHER.is_file(), f"missing launcher at {_LAUNCHER}"

    def test_launcher_is_executable(self):
        assert os.access(_LAUNCHER, os.X_OK), "launcher must have the +x bit"

    def test_launcher_invokes_venv_python_and_script(self):
        text = _LAUNCHER.read_text()
        assert "scripts/classify/venv/bin/python" in text
        assert "scripts/classify/control_panel.py" in text

    def test_launcher_port_matches_panel_default(self):
        # The port the launcher opens MUST equal the port the server binds,
        # or double-click opens a dead URL.
        text = _LAUNCHER.read_text()
        assert str(cp._DEFAULT_PORT) in text

    def test_launcher_opens_the_browser(self):
        text = _LAUNCHER.read_text()
        assert "open " in text and "127.0.0.1" in text
