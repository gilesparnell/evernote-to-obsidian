"""Structured output extraction for OpenAI-compatible local LLMs."""

from __future__ import annotations

import json
import re
from typing import TypeVar

from pydantic import BaseModel, ValidationError

T = TypeVar("T", bound=BaseModel)

_SCHEMA_INSTRUCTION = """\
You MUST respond with ONLY valid JSON. No prose before or after.
Return the JSON object directly. Do NOT wrap it or add extra keys.

Fill in this exact JSON structure with real content:

{template}

Replace each placeholder string with actual content. Keep the same keys and types.
Respond with nothing but the completed JSON object."""


class StructuredOutputError(Exception):
    """Raised when an LLM response cannot be parsed into the requested model."""


def _resolve_ref(node: dict, defs: dict) -> dict:
    if "$ref" not in node:
        return node
    key = node["$ref"].rsplit("/", 1)[-1]
    resolved = defs.get(key)
    return resolved if isinstance(resolved, dict) else node


def _render_example(node: dict, defs: dict, field_name: str = "") -> object:
    node = _resolve_ref(node, defs)

    if "anyOf" in node and "type" not in node:
        outer_desc = node.get("description", "")
        for alt in node["anyOf"]:
            if alt.get("type") != "null":
                if outer_desc and "description" not in alt:
                    alt = {**alt, "description": outer_desc}
                return _render_example(alt, defs, field_name)
        return None

    field_type = node.get("type")
    description = node.get("description", "")
    enum = node.get("enum")

    if enum:
        return " | ".join(str(item) for item in enum)
    if field_type == "array":
        items = _resolve_ref(node.get("items", {}), defs)
        if items.get("type") == "object" or "properties" in items:
            return [_render_example(items, defs, field_name)]
        return [description[:60] or f"<{field_name} item>"]
    if field_type == "object" or "properties" in node:
        return {
            sub_name: _render_example(sub_node, defs, sub_name)
            for sub_name, sub_node in node.get("properties", {}).items()
        }
    if field_type in {"integer", "number"}:
        return 0
    if field_type == "boolean":
        return True
    return description[:80] or f"<{field_name}>"


def _make_template(model_class: type[T]) -> str:
    schema = model_class.model_json_schema()
    defs = schema.get("$defs", {}) or schema.get("definitions", {})
    props = schema.get("properties", {})
    template = {
        name: _render_example(field_schema, defs, name)
        for name, field_schema in props.items()
    }
    return json.dumps(template, indent=2)


def _schema_system(model_class: type[T]) -> str:
    return _SCHEMA_INSTRUCTION.format(template=_make_template(model_class))


def _extract_json(text: str) -> str | None:
    fenced = re.search(r"```(?:json)?\s*\n(.*?)\n\s*```", text, re.DOTALL | re.IGNORECASE)
    if fenced:
        return fenced.group(1).strip()

    return _extract_first_balanced_object(text)


def _extract_first_balanced_object(text: str) -> str | None:
    start = text.find("{")
    if start == -1:
        return None

    depth = 0
    in_string = False
    escaped = False
    for idx in range(start, len(text)):
        char = text[idx]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : idx + 1].strip()

    return None


def _looks_like_schema_echo(data: dict) -> bool:
    props = data.get("properties")
    if not isinstance(props, dict):
        return False
    return data.get("type") == "object" or any(
        isinstance(value, dict) and "type" in value
        for value in props.values()
    )


def _coerce_json_string_fields(data: dict, model_class: type[T]) -> dict:
    coerced = dict(data)
    for field_name in model_class.model_fields:
        value = coerced.get(field_name)
        if not isinstance(value, str):
            continue
        stripped = value.strip()
        if not stripped or stripped[0] not in "[{":
            continue
        try:
            parsed = json.loads(stripped)
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(parsed, (dict, list)):
            coerced[field_name] = parsed
    return coerced


def _unwrap(data: dict, model_class: type[T]) -> dict:
    if not isinstance(data, dict):
        return data

    if len(data) == 1:
        value = next(iter(data.values()))
        if isinstance(value, dict):
            data = value
        elif isinstance(value, str):
            try:
                parsed = json.loads(value)
            except (json.JSONDecodeError, ValueError):
                parsed = None
            if isinstance(parsed, dict):
                data = parsed

    if "properties" in data and isinstance(data["properties"], dict) and not _looks_like_schema_echo(data):
        data = data["properties"]

    return _coerce_json_string_fields(data, model_class)


def _try_parse(raw: str, model_class: type[T]) -> tuple[T | None, str]:
    if raw is None or raw == "":
        return None, "Empty response content"

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        if "Invalid \\escape" in str(exc):
            try:
                data = json.loads(re.sub(r"\\(?![\"\\/bfnrtu])", r"\\\\", raw))
            except json.JSONDecodeError:
                return None, f"Invalid JSON: {exc}"
        else:
            return None, f"Invalid JSON: {exc}"

    if isinstance(data, dict) and _looks_like_schema_echo(data):
        return None, "Model returned JSON schema instead of data"

    last_error = ""
    try:
        return model_class.model_validate(data), ""
    except ValidationError as exc:
        last_error = str(exc)

    try:
        unwrapped = _unwrap(data, model_class)
        if isinstance(unwrapped, dict) and _looks_like_schema_echo(unwrapped):
            return None, "Model returned JSON schema instead of data"
        return model_class.model_validate(unwrapped), ""
    except ValidationError as exc:
        last_error = str(exc)
    except Exception as exc:
        last_error = f"{type(exc).__name__}: {exc}"

    return None, last_error


def _content_from_response(response) -> str | None:
    try:
        return response.choices[0].message.content
    except (AttributeError, IndexError, TypeError) as exc:
        raise StructuredOutputError(f"Malformed OpenAI response: {type(exc).__name__}: {exc}") from exc


def generate_structured(
    client,
    model: str,
    system: str,
    prompt: str,
    output_model: type[T],
    max_retries: int = 2,
) -> T:
    """Generate and parse structured output using an OpenAI-compatible client."""

    schema_system = _schema_system(output_model)
    full_system = f"{system}\n\n{schema_system}" if system.strip() else schema_system
    messages = [
        {"role": "system", "content": full_system},
        {"role": "user", "content": prompt},
    ]
    last_error = ""

    for attempt in range(max_retries + 1):
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0,
            response_format={"type": "json_object"},
        )
        raw = _content_from_response(response)
        parse_raw = raw if isinstance(raw, str) else ""

        result, parse_error = _try_parse(parse_raw, output_model)
        if result is not None:
            return result
        last_error = parse_error

        extracted = _extract_json(parse_raw)
        if extracted:
            result, parse_error = _try_parse(extracted, output_model)
            if result is not None:
                return result
            if parse_error:
                last_error = parse_error

        if attempt < max_retries:
            messages = [
                *messages,
                {"role": "assistant", "content": parse_raw},
                {
                    "role": "user",
                    "content": (
                        "Your previous response was invalid.\n"
                        f"Error: {last_error}\n\n"
                        f"Original request:\n{prompt}\n\n"
                        "Respond with ONLY valid JSON matching the template. Nothing else."
                    ),
                },
            ]

    raise StructuredOutputError(
        f"Failed to get valid {output_model.__name__} after {max_retries + 1} attempts. "
        f"Last error: {last_error}"
    )
