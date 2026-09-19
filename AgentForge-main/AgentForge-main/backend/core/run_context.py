from __future__ import annotations

import contextvars
from dataclasses import dataclass

_current_run_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "current_run_id", default=None
)


def set_current_run_id(run_id: str | None) -> None:

    _current_run_id.set(run_id)


def get_current_run_id() -> str | None:
    return _current_run_id.get()


@dataclass(frozen=True)
class LLMCallInfo:
    provider: str | None
    model: str | None
    provider_request_id: str | None
    input_tokens: int | None
    output_tokens: int | None
    prompt_characters: int
    response_characters: int


_llm_calls: contextvars.ContextVar[list[LLMCallInfo] | None] = contextvars.ContextVar(
    "current_node_llm_calls", default=None
)


def reset_llm_calls() -> None:
    _llm_calls.set([])


def record_llm_call(info: LLMCallInfo) -> None:
    calls = _llm_calls.get()

    if calls is None:
        calls = []
        _llm_calls.set(calls)

    calls.append(info)


def drain_llm_calls() -> list[LLMCallInfo]:
    calls = _llm_calls.get() or []
    _llm_calls.set([])

    return calls
