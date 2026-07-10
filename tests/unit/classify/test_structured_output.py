from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from scripts.classify.structured_output import (
    StructuredOutputError,
    _try_parse,
    generate_structured,
)


class Demo(BaseModel):
    summary: str
    tags: list[str]


class FakeCompletions:
    def __init__(self, responses: list[str | None]) -> None:
        self._responses = responses
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if not self._responses:
            raise AssertionError("Fake client received more calls than scripted")
        content = self._responses.pop(0)
        message = SimpleNamespace(content=content)
        choice = SimpleNamespace(message=message)
        return SimpleNamespace(choices=[choice])


class FakeClient:
    def __init__(self, responses: list[str | None]) -> None:
        self.chat = SimpleNamespace(
            completions=FakeCompletions(responses),
        )

    @property
    def calls(self) -> list[dict]:
        return self.chat.completions.calls


def generate(client: FakeClient, max_retries: int = 2) -> Demo:
    return generate_structured(
        client=client,
        model="google/gemma-4-e4b",
        system="You summarize notes.",
        prompt="Summarize this note.",
        output_model=Demo,
        max_retries=max_retries,
    )


def test_tier_1_clean_json_parses_first_try() -> None:
    client = FakeClient(['{"summary":"Clean","tags":["one","two"]}'])

    result = generate(client)

    assert result == Demo(summary="Clean", tags=["one", "two"])
    assert len(client.calls) == 1
    assert client.calls[0]["model"] == "google/gemma-4-e4b"
    assert client.calls[0]["temperature"] == 0
    assert client.calls[0]["messages"][0]["role"] == "system"
    assert "Fill in this exact JSON structure" in client.calls[0]["messages"][0]["content"]


def test_does_not_send_json_object_response_format() -> None:
    """LM Studio 400s on response_format.type='json_object' (only json_schema/text).

    The 3-tier parser extracts JSON from plain text, so we must not pin the
    unsupported json_object mode. Regression guard for the T7 live 400.
    """
    client = FakeClient(['{"summary":"Clean","tags":["one"]}'])

    generate(client)

    rf = client.calls[0].get("response_format")
    assert rf is None or rf.get("type") != "json_object"


def test_tier_2_fenced_json_is_extracted_and_parsed() -> None:
    client = FakeClient(['```json\n{"summary":"Fenced","tags":["json"]}\n```'])

    result = generate(client)

    assert result == Demo(summary="Fenced", tags=["json"])
    assert len(client.calls) == 1


def test_tier_2_balanced_braced_json_is_extracted_from_prose() -> None:
    client = FakeClient(['Here is the result: {"summary":"Braced","tags":["prose"]} Thanks.'])

    result = generate(client)

    assert result == Demo(summary="Braced", tags=["prose"])
    assert len(client.calls) == 1


def test_tier_3_retries_with_validation_error_feedback() -> None:
    client = FakeClient([
        '{"summary":"Missing tags"}',
        '{"summary":"Recovered","tags":["retry"]}',
    ])

    result = generate(client)

    assert result == Demo(summary="Recovered", tags=["retry"])
    assert len(client.calls) == 2
    retry_messages = client.calls[1]["messages"]
    assert retry_messages[-2] == {"role": "assistant", "content": '{"summary":"Missing tags"}'}
    assert retry_messages[-1]["role"] == "user"
    assert "previous response was invalid" in retry_messages[-1]["content"]
    assert "tags" in retry_messages[-1]["content"]


def test_unwraps_single_key_wrapper() -> None:
    parsed, error = _try_parse('{"Demo":{"summary":"Wrapped","tags":["demo"]}}', Demo)

    assert error == ""
    assert parsed == Demo(summary="Wrapped", tags=["demo"])


def test_coerces_json_string_fields() -> None:
    parsed, error = _try_parse('{"summary":"String field","tags":"[\\"alpha\\", \\"beta\\"]"}', Demo)

    assert error == ""
    assert parsed == Demo(summary="String field", tags=["alpha", "beta"])


def test_schema_echo_raises_structured_output_error() -> None:
    client = FakeClient([json.dumps(Demo.model_json_schema())])

    with pytest.raises(StructuredOutputError) as exc_info:
        generate(client, max_retries=0)

    assert "schema" in str(exc_info.value).lower() or "field required" in str(exc_info.value).lower()


def test_empty_and_none_content_are_retryable_failures_not_type_errors() -> None:
    client = FakeClient([
        "",
        None,
        '{"summary":"Recovered from empty","tags":["overflow"]}',
    ])

    result = generate(client, max_retries=2)

    assert result == Demo(summary="Recovered from empty", tags=["overflow"])
    assert len(client.calls) == 3
    assert "empty response" in client.calls[1]["messages"][-1]["content"].lower()


def test_failure_after_retries_raises_with_last_error() -> None:
    client = FakeClient([
        '{"summary":"Missing tags"}',
        "not json",
        "",
    ])

    with pytest.raises(StructuredOutputError) as exc_info:
        generate(client, max_retries=2)

    message = str(exc_info.value)
    assert "Failed to get valid Demo after 3 attempts" in message
    assert "empty response" in message.lower()
