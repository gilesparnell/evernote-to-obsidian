"""Smoke tests that every classifier CLI ships a rich --help block.

Each CLI must produce a 'Common patterns' section in its --help so the
runbook can reference --help directly rather than duplicating flag docs.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_VENV_PYTHON = _REPO_ROOT / "scripts" / "classify" / "venv" / "bin" / "python"

CLI_MODULES = [
    "scripts.classify.classify_vault",
    "scripts.classify.migrate_legacy_up",
    "scripts.classify.migrate_vault",
    "scripts.classify.sample_classified",
]


@pytest.mark.parametrize("module", CLI_MODULES)
def test_cli_help_contains_common_patterns_section(module: str) -> None:
    """The CLI's --help output must contain a 'Common patterns' header."""
    result = subprocess.run(
        [str(_VENV_PYTHON), "-m", module, "--help"],
        cwd=str(_REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, (
        f"--help exited with {result.returncode} for {module}\n"
        f"stderr: {result.stderr}\nstdout: {result.stdout}"
    )
    assert "Common patterns" in result.stdout, (
        f"{module} --help missing 'Common patterns' section.\n"
        f"stdout:\n{result.stdout}"
    )


@pytest.mark.parametrize(
    "module",
    [
        "scripts.classify.classify_vault",
        "scripts.classify.migrate_vault",
        "scripts.classify.sample_classified",
    ],
)
def test_cli_can_be_run_as_script_path(module: str) -> None:
    """`python scripts/classify/<name>.py --help` (script path) must work.

    Sanity check that the sys.path bootstrap makes direct script invocation
    succeed for CLIs that import from the scripts.classify package.
    """
    script_path = _REPO_ROOT / (module.replace(".", "/") + ".py")
    result = subprocess.run(
        [str(_VENV_PYTHON), str(script_path), "--help"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, (
        f"Direct script invocation failed for {script_path}\n"
        f"stderr: {result.stderr}"
    )
