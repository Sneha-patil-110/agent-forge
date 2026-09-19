from __future__ import annotations

import json
from typing import Any

from backend.core.exceptions import (
    AgentOutputEmptyError,
    AgentOutputInvalidJSONError,
    AgentOutputSchemaError,
    AgentOutputTruncatedError,
    AgentValidationError,
)

_EXCERPT_RADIUS = 200
_FENCE_OPENERS = {"```", "```json", "```JSON"}
_VALID_JSON_ESCAPES = set('"\\/bfnrtu')


def parse_json_object(
    content: Any,
    *,
    agent_name: str,
    response_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if response_metadata:
        finish_reason = response_metadata.get("finish_reason") or response_metadata.get("stop_reason")
        if finish_reason in ("length", "max_tokens"):
            raise AgentOutputTruncatedError(
                f"{agent_name} Agent response was truncated due to provider output token limits.",
                details={"agent": agent_name, "finish_reason": finish_reason},
            )

    if content is None:
        raise AgentOutputEmptyError(
            f"{agent_name} Agent returned no content (None).",
            details={"agent": agent_name, "response_length": 0},
        )

    if not isinstance(content, str):
        raise AgentValidationError(
            f"{agent_name} Agent returned a non textual response.",
            details={"agent": agent_name, "response_type": type(content).__name__},
        )

    text = content.strip()

    if not text:
        raise AgentOutputEmptyError(
            f"{agent_name} Agent returned an empty response.",
            details={"agent": agent_name, "response_length": 0},
        )

    text = _strip_code_fence(text)
    text = _locate_json_object(text)

    if not text.strip():
        raise AgentOutputEmptyError(
            f"{agent_name} Agent code fence contained no content.",
            details={"agent": agent_name, "response_length": 0},
        )

    try:
        data, _end_index = json.JSONDecoder().raw_decode(text)

    except json.JSONDecodeError as error:
        if "escape" in error.msg.lower():
            try:
                data, _end_index = json.JSONDecoder().raw_decode(_escape_stray_backslashes(text))
            except json.JSONDecodeError:
                pass
            else:
                if not isinstance(data, dict):
                    raise AgentOutputSchemaError(
                        f"{agent_name} Agent response must be a single JSON object, "
                        f"received {type(data).__name__}.",
                        details={"agent": agent_name, "response_type": type(data).__name__},
                    ) from None

                return data

        start = max(error.pos - _EXCERPT_RADIUS, 0)
        end = min(error.pos + _EXCERPT_RADIUS, len(text))

        raise AgentOutputInvalidJSONError(
            f"{agent_name} Agent returned invalid JSON: {error.msg}",
            details={
                "agent": agent_name,
                "line": error.lineno,
                "column": error.colno,
                "position": error.pos,
                "excerpt": text[start:end],
                "error_msg": error.msg,
            },
        ) from error

    if not isinstance(data, dict):
        raise AgentOutputSchemaError(
            f"{agent_name} Agent response must be a single JSON object, received {type(data).__name__}.",
            details={"agent": agent_name, "response_type": type(data).__name__},
        )

    return data



def _locate_json_object(text: str) -> str:

    if text.startswith("{"):
        return text

    brace_index = text.find("{")

    if brace_index == -1:
        return text

    return text[brace_index:]


def _strip_code_fence(text: str) -> str:

    if not text.startswith("```"):
        return text

    lines = text.splitlines()

    if lines and lines[0].strip() in _FENCE_OPENERS:
        lines = lines[1:]

    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]

    return "\n".join(lines).strip()


def _escape_stray_backslashes(text: str) -> str:
    result: list[str] = []
    in_string = False
    i = 0
    length = len(text)

    while i < length:
        char = text[i]

        if in_string and char == "\\":
            next_char = text[i + 1] if i + 1 < length else ""

            if next_char in _VALID_JSON_ESCAPES:
                result.append(char)
                result.append(next_char)
                i += 2
            else:
                result.append("\\\\")
                i += 1

            continue

        if char == '"':
            in_string = not in_string

        result.append(char)
        i += 1

    return "".join(result)
