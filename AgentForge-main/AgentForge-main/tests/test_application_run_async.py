
from __future__ import annotations

import asyncio

import pytest

from backend.core.app import Application, _run_async


def test_run_async_returns_the_coroutines_result_without_a_running_loop() -> None:
    async def coro() -> int:
        return 42

    assert _run_async(coro()) == 42


def test_run_async_returns_the_coroutines_result_with_a_running_loop() -> None:
    async def inner() -> int:
        return 42

    async def outer() -> int:
        return _run_async(inner())

    assert asyncio.run(outer()) == 42


def test_run_async_propagates_exceptions_without_a_running_loop() -> None:
    async def coro() -> None:
        raise ValueError("boom")

    with pytest.raises(ValueError, match="boom"):
        _run_async(coro())


def test_run_async_propagates_exceptions_with_a_running_loop() -> None:
    async def inner() -> None:
        raise ValueError("boom")

    async def outer() -> None:
        _run_async(inner())

    with pytest.raises(ValueError, match="boom"):
        asyncio.run(outer())


def test_application_construction_and_shutdown_work_from_within_a_running_event_loop() -> None:

    async def scenario() -> None:
        application = Application()
        try:
            assert "local-tools" in application.mcp_client_manager.enabled_server_names()
        finally:
            application.shutdown()

    asyncio.run(scenario())
