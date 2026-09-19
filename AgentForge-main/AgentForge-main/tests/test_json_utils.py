from __future__ import annotations

import json

import pytest

from backend.core.exceptions import AgentValidationError
from backend.utils.json_utils import parse_json_object


def test_parses_plain_json_object() -> None:
    data = parse_json_object('{"a": 1, "b": [1, 2]}', agent_name="Test")

    assert data == {"a": 1, "b": [1, 2]}


def test_strips_surrounding_whitespace() -> None:
    data = parse_json_object('  \n {"a": 1}\n  ', agent_name="Test")

    assert data == {"a": 1}


def test_strips_single_markdown_code_fence() -> None:
    content = '```json\n{"a": 1}\n```'

    data = parse_json_object(content, agent_name="Test")

    assert data == {"a": 1}


def test_does_not_modify_valid_json_without_fence() -> None:
    content = '{"a": "```not a fence```"}'

    data = parse_json_object(content, agent_name="Test")

    assert data == {"a": "```not a fence```"}


def test_rejects_non_string_content() -> None:
    with pytest.raises(AgentValidationError):
        parse_json_object(None, agent_name="Test")


def test_rejects_empty_content() -> None:
    with pytest.raises(AgentValidationError):
        parse_json_object("   ", agent_name="Test")


def test_rejects_json_array() -> None:
    with pytest.raises(AgentValidationError):
        parse_json_object("[1, 2, 3]", agent_name="Test")


def test_rejects_json_primitive() -> None:
    with pytest.raises(AgentValidationError):
        parse_json_object("42", agent_name="Test")


def test_invalid_json_error_includes_location_details() -> None:
    with pytest.raises(AgentValidationError) as exc_info:
        parse_json_object('{"a": 1,}', agent_name="Analysis")

    error = exc_info.value

    assert error.details is not None
    assert "line" in error.details
    assert "column" in error.details
    assert "position" in error.details
    assert "excerpt" in error.details
    assert "Analysis" in error.message


def test_rejects_truncated_json() -> None:
    with pytest.raises(AgentValidationError):
        parse_json_object('{"a": 1, "b": [1, 2', agent_name="Developer")


def test_rejects_plain_text() -> None:
    with pytest.raises(AgentValidationError):
        parse_json_object(
            "Sure, here is the analysis you requested.",
            agent_name="Analysis",
        )


def test_parses_json_with_escaped_newlines() -> None:
    content = '{"notes": "line one\\nline two\\nline three"}'

    data = parse_json_object(content, agent_name="Developer")

    assert data == {"notes": "line one\nline two\nline three"}


def test_parses_json_containing_source_code_string() -> None:
    payload = {
        "generated_code": [
            {
                "path": "app.py",
                "content": (
                    "def add(a, b):\n"
                    "    \"\"\"Return a + b.\"\"\"\n"
                    "    return a + b\n"
                ),
                "language": "python",
                "description": "Addition helper.",
            }
        ],
        "completed_tasks": ["T1"],
        "failed_tasks": [],
        "implementation_notes": None,
    }

    content = json.dumps(payload)

    data = parse_json_object(content, agent_name="Developer")

    assert "def add(a, b):" in data["generated_code"][0]["content"]


def test_parses_json_containing_markdown_documentation_string() -> None:
    payload = {
        "generated_docs": [
            {
                "title": "README",
                "path": "README.md",
                "content": "# Project\n\n## Installation\n\n```bash\npip install -r requirements.txt\n```\n",
                "description": "Project overview.",
            }
        ],
        "documentation_summary": "Generated README.",
        "pending_documentation": [],
    }

    content = json.dumps(payload)

    data = parse_json_object(content, agent_name="Documentation")

    assert "```bash" in data["generated_docs"][0]["content"]


def test_tolerates_trailing_commentary_after_a_complete_object() -> None:

    content = '{"a": 1}\n\nHope that helps! Let me know if you need anything else.'

    data = parse_json_object(content, agent_name="Tester")

    assert data == {"a": 1}


def test_still_rejects_malformed_json_even_with_no_trailing_content() -> None:
    with pytest.raises(AgentValidationError):
        parse_json_object('{"a": 1, "b": }', agent_name="Test")


def test_strips_code_fence_around_json_containing_own_backticks() -> None:
    inner_content = "Use ```python\ncode\n``` in docs."
    inner = json.dumps({"content": inner_content})
    wrapped = f"```json\n{inner}\n```"

    data = parse_json_object(wrapped, agent_name="Documentation")

    assert data["content"] == inner_content


def test_repairs_unescaped_windows_path_backslash() -> None:
    content = '{"explanation": "See C:\\Users\\dev\\app.py for the fix."}'

    data = parse_json_object(content, agent_name="Debugger")

    assert data["explanation"] == r"See C:\Users\dev\app.py for the fix."


def test_repairs_unescaped_regex_backslash() -> None:
    content = '{"pattern": "\\d+\\s*\\w"}'

    data = parse_json_object(content, agent_name="Debugger")

    assert data["pattern"] == r"\d+\s*\w"


def test_repair_still_honors_valid_escapes_alongside_stray_ones() -> None:
    content = '{"notes": "line one\\nC:\\Users\\dev has a \\"quoted\\" path"}'

    data = parse_json_object(content, agent_name="Debugger")

    assert data["notes"] == 'line one\nC:\\Users\\dev has a "quoted" path'


def test_repair_falls_back_to_original_error_when_still_unparseable() -> None:
    content = '{"a": "\\q", "b": }'

    with pytest.raises(AgentValidationError) as exc_info:
        parse_json_object(content, agent_name="Test")

    assert "Test" in exc_info.value.message
    assert "escape" in exc_info.value.message.lower()
