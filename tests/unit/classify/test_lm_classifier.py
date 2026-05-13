"""Unit tests for scripts.classify.lm_classifier.

Covers the six scenarios from plan §Unit 4 — all run against a mocked
openai.OpenAI client. No network calls. The live smoke tests live
separately under tests/integration/classify/test_lm_classifier_live.py.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from scripts.classify.lm_classifier import classify


def _make_response(arguments_json: str | None) -> MagicMock:
    """Build a mock OpenAI completion response.

    If arguments_json is None, the response has no tool_calls (LM Studio
    fell back to a text reply). Otherwise tool_calls[0].function.arguments
    is set to arguments_json.
    """
    response = MagicMock()
    if arguments_json is None:
        response.choices[0].message.tool_calls = []
    else:
        tool_call = MagicMock()
        tool_call.function.arguments = arguments_json
        response.choices[0].message.tool_calls = [tool_call]
    return response


def _patch_openai(response_or_exception):
    """Return a patch() context manager that replaces openai.OpenAI with a
    mock whose chat.completions.create returns the given response (or raises
    the given exception when side_effect is used)."""
    patcher = patch("scripts.classify.lm_classifier.openai.OpenAI")
    mock_cls = patcher.start()
    mock_client = mock_cls.return_value
    if isinstance(response_or_exception, BaseException):
        mock_client.chat.completions.create.side_effect = response_or_exception
    else:
        mock_client.chat.completions.create.return_value = response_or_exception
    return patcher


class TestLMClassifier:
    def test_valid_tool_call_response_extracts_all_r2_fields(self) -> None:
        args = json.dumps({
            "type": "meeting",
            "org": "Amazon",
            "context": "work",
            "people": ["Alice Smith"],
            "tags": ["star"],
            "confidence": 0.9,
            "reason": "AWS standup meeting",
        })
        patcher = _patch_openai(_make_response(args))
        try:
            result = classify("Weekly standup", "AWS EC2 capacity planning", "AWS")
        finally:
            patcher.stop()

        assert result["type"] == "meeting"
        assert result["org"] == "Amazon"
        assert result["context"] == "work"
        assert result["people"] == ["Alice Smith"]
        assert result["tags"] == ["star"]
        assert result["confidence"] == 0.9

    def test_no_tool_calls_returns_zero_confidence_without_raising(self) -> None:
        # LM Studio fell back to a plain text reply (no tool_calls).
        patcher = _patch_openai(_make_response(arguments_json=None))
        try:
            result = classify("title", "body", "")
        finally:
            patcher.stop()

        assert result["confidence"] == 0.0
        assert "lm-studio" in result["reason"].lower()

    def test_connection_error_returns_zero_confidence_without_raising(self) -> None:
        patcher = _patch_openai(ConnectionError("server down"))
        try:
            result = classify("title", "body", "")
        finally:
            patcher.stop()

        assert result["confidence"] == 0.0
        assert "lm-studio" in result["reason"].lower()

    def test_missing_people_defaults_to_empty_list(self) -> None:
        args = json.dumps({
            "type": "meeting",
            "org": "Amazon",
            "context": "work",
            # people deliberately omitted
            "tags": [],
            "confidence": 0.8,
            "reason": "ok",
        })
        patcher = _patch_openai(_make_response(args))
        try:
            result = classify("t", "b", "")
        finally:
            patcher.stop()

        assert result["people"] == []

    def test_missing_tags_defaults_to_empty_list(self) -> None:
        args = json.dumps({
            "type": "meeting",
            "org": "Amazon",
            "context": "work",
            "people": [],
            # tags deliberately omitted
            "confidence": 0.8,
            "reason": "ok",
        })
        patcher = _patch_openai(_make_response(args))
        try:
            result = classify("t", "b", "")
        finally:
            patcher.stop()

        assert result["tags"] == []

    def test_confidence_above_one_clamps_to_one(self) -> None:
        args = json.dumps({
            "type": "meeting",
            "org": "Amazon",
            "context": "work",
            "people": [],
            "tags": [],
            "confidence": 1.5,  # impossible — must be clamped
            "reason": "model produced out-of-range confidence",
        })
        patcher = _patch_openai(_make_response(args))
        try:
            result = classify("t", "b", "")
        finally:
            patcher.stop()

        assert result["confidence"] == 1.0
