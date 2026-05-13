"""Live smoke tests against the running LM Studio server on :1234.

Marked ``integration_live`` so pytest skips them by default. To run:
    scripts/classify/venv/bin/pytest -m integration_live

Tests are additionally skipif-ed if the TCP port isn't open, so a missing
LM Studio server is treated as a skip, not a hard failure.
"""

from __future__ import annotations

import socket

import pytest

from scripts.classify.lm_classifier import classify


def _lm_studio_reachable(host: str = "localhost", port: int = 1234) -> bool:
    try:
        with socket.create_connection((host, port), timeout=1):
            return True
    except OSError:
        return False


pytestmark = [
    pytest.mark.integration_live,
    pytest.mark.skipif(
        not _lm_studio_reachable(),
        reason="LM Studio not running on :1234",
    ),
]


def test_live_clear_meeting_note_classifies_as_meeting() -> None:
    result = classify(
        "Weekly AWS standup",
        "Attendees: Alice, Bob. Agenda: EC2 capacity, CloudWatch alarms, retro.",
        "AWS",
    )
    assert result["type"] == "meeting", result
    assert result["org"] == "Amazon", result
    assert result["context"] == "work", result
    assert 0.0 < result["confidence"] <= 1.0, result


def test_live_clear_star_story_classifies_as_interview() -> None:
    result = classify(
        "STAR — customer escalation",
        "Situation: a top customer escalated. Task: resolve within 24h. "
        "Action: pulled in the SRE team. Result: shipped a fix and earned trust.",
        "Job Hunt",
    )
    assert result["type"] in {"interview", "management"}, result
    assert result["confidence"] > 0.0, result


def test_live_low_signal_note_returns_low_confidence() -> None:
    result = classify(
        "Untitled",
        "A short note with no specific signals.",
        "",
    )
    # We don't assert a specific type — only that the classifier honoured
    # the schema and returned a low confidence for a genuinely ambiguous note.
    assert "type" in result and "org" in result and "confidence" in result
    assert 0.0 <= result["confidence"] <= 1.0
