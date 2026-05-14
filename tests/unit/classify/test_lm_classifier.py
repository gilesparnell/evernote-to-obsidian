"""Unit tests for scripts.classify.lm_classifier.

Covers the six scenarios from plan §Unit 4 — all run against a mocked
openai.OpenAI client. No network calls. The live smoke tests live
separately under tests/integration/classify/test_lm_classifier_live.py.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from scripts.classify.lm_classifier import classify


@pytest.fixture(autouse=True)
def _reset_client_cache() -> None:
    """The lm_classifier caches its openai.OpenAI() instance at module level
    (singleton, fixes the FD-exhaustion regression from 2026-05-14). Tests
    need a fresh cache each time so their patched openai.OpenAI is the one
    that gets instantiated.
    """
    from scripts.classify.lm_classifier import _get_client
    _get_client.cache_clear()


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


class TestSingletonClientLifecycle:
    """Regression: 2026-05-14 PM run crashed at ~297 LM calls with
    OSError [Errno 24] 'Too many open files'. Root cause: openai.OpenAI()
    was instantiated inside classify() on every call, leaking httpx
    connection-pool FDs. The fix is a module-level singleton — tested
    here by patching openai.OpenAI and confirming only one instantiation
    occurs across many classify() calls.
    """

    def test_classify_instantiates_openai_once_across_many_calls(self) -> None:
        args = json.dumps({
            "type": "note",
            "org": "Amazon",
            "context": "work",
            "people": [],
            "tags": [],
            "confidence": 0.9,
            "reason": "ok",
        })
        patcher = _patch_openai(_make_response(args))
        try:
            mock_cls = patch("scripts.classify.lm_classifier.openai.OpenAI")
            # _patch_openai already started a patch; reuse its mock.
            for _ in range(50):
                classify("t", "b", "")
            from scripts.classify.lm_classifier import openai as patched_openai
            # The mock was applied to the module's openai.OpenAI attribute;
            # its call_count is the number of instantiations.
            assert patched_openai.OpenAI.call_count == 1, (
                f"Expected 1 instantiation across 50 classify() calls, "
                f"got {patched_openai.OpenAI.call_count}. "
                "This regression burns file descriptors and crashes the "
                "pipeline at ~250-300 LM calls."
            )
            del mock_cls  # silence unused-warning; patcher is the one in use
        finally:
            patcher.stop()

    def test_get_client_returns_same_instance_on_repeat_calls(self) -> None:
        """Direct test on the cache: _get_client() must be idempotent."""
        patcher = _patch_openai(_make_response(None))
        try:
            from scripts.classify.lm_classifier import _get_client
            first = _get_client()
            second = _get_client()
            assert first is second
        finally:
            patcher.stop()
