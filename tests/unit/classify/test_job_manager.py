"""Unit tests for the control panel's JobManager.

Scripts like classify_vault run for hours, so execution must be async: a run
spawns a subprocess and returns a job_id immediately; a background thread
tracks state (running → complete/failed) + captures output. One job at a
time (v1) so two classify_vault runs can't race on the vault.

Tests use trivial fast commands (the venv/system python with -c) so they
never touch the real vault.
"""

from __future__ import annotations

import sys
import time

from scripts.classify.control_panel import JobManager


def _entry(argv, interpreter=sys.executable, cwd="."):
    """A fake registry entry that runs a quick python snippet."""
    return {
        "key": "test-job",
        "interpreter": interpreter,
        "cwd": cwd,
        "argv": argv,
    }


def _wait_done(jm, job_id, timeout=10.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        st = jm.get_status(job_id)
        if st["state"] != "running":
            return st
        time.sleep(0.02)
    raise AssertionError(f"job {job_id} did not finish within {timeout}s")


class TestStartJob:
    def test_returns_a_job_id_string(self):
        jm = JobManager()
        job_id = jm.start_job("test-job", _entry(["-c", "print('hi')"]))
        assert isinstance(job_id, str) and job_id
        _wait_done(jm, job_id)

    def test_successful_job_reaches_complete_with_exit_zero(self):
        jm = JobManager()
        job_id = jm.start_job("test-job", _entry(["-c", "print('hi')"]))
        st = _wait_done(jm, job_id)
        assert st["state"] == "complete"
        assert st["exit_code"] == 0
        assert "hi" in st["output"]

    def test_failing_job_reaches_failed_with_nonzero_exit(self):
        jm = JobManager()
        job_id = jm.start_job(
            "test-job", _entry(["-c", "import sys; sys.exit(3)"]),
        )
        st = _wait_done(jm, job_id)
        assert st["state"] == "failed"
        assert st["exit_code"] == 3

    def test_captures_multiline_output(self):
        jm = JobManager()
        job_id = jm.start_job(
            "test-job", _entry(["-c", "print('line1'); print('line2')"]),
        )
        st = _wait_done(jm, job_id)
        assert "line1" in st["output"]
        assert "line2" in st["output"]

    def test_captures_stderr_too(self):
        jm = JobManager()
        job_id = jm.start_job(
            "test-job",
            _entry(["-c", "import sys; print('to stderr', file=sys.stderr)"]),
        )
        st = _wait_done(jm, job_id)
        assert "to stderr" in st["output"]

    def test_status_includes_key_and_started_at(self):
        jm = JobManager()
        job_id = jm.start_job("test-job", _entry(["-c", "print('x')"]))
        st = jm.get_status(job_id)
        assert st["key"] == "test-job"
        assert st["started_at"]
        _wait_done(jm, job_id)


class TestRunningState:
    def test_state_is_running_immediately_after_start(self):
        jm = JobManager()
        job_id = jm.start_job(
            "test-job", _entry(["-c", "import time; time.sleep(0.4)"]),
        )
        # Right after start, before the sleep finishes.
        assert jm.get_status(job_id)["state"] == "running"
        _wait_done(jm, job_id)

    def test_is_busy_true_while_running_false_after(self):
        jm = JobManager()
        job_id = jm.start_job(
            "test-job", _entry(["-c", "import time; time.sleep(0.3)"]),
        )
        assert jm.is_busy() is True
        _wait_done(jm, job_id)
        assert jm.is_busy() is False


class TestOneAtATime:
    def test_start_while_busy_raises(self):
        import pytest
        jm = JobManager()
        first = jm.start_job(
            "test-job", _entry(["-c", "import time; time.sleep(0.4)"]),
        )
        with pytest.raises(RuntimeError, match="busy|already running|in progress"):
            jm.start_job("test-job-2", _entry(["-c", "print('x')"]))
        _wait_done(jm, first)

    def test_can_start_new_job_after_previous_completes(self):
        jm = JobManager()
        first = jm.start_job("test-job", _entry(["-c", "print('one')"]))
        _wait_done(jm, first)
        second = jm.start_job("test-job", _entry(["-c", "print('two')"]))
        st = _wait_done(jm, second)
        assert "two" in st["output"]


class TestGetStatus:
    def test_unknown_job_id_raises(self):
        import pytest
        jm = JobManager()
        with pytest.raises(KeyError):
            jm.get_status("no-such-job")
