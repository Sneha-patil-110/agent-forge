from __future__ import annotations

import asyncio
import logging
import threading
from typing import Any, Awaitable, TypeVar

logger = logging.getLogger(__name__)

_T = TypeVar("_T")


class MCPLoopRunner:

    _instance: MCPLoopRunner | None = None
    _lock = threading.Lock()

    def __init__(self) -> None:
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=self._run_loop,
            name="mcp_event_loop_thread",
            daemon=True,
        )
        self._thread.start()
        logger.info("MCPLoopRunner initialized with background thread '%s'", self._thread.name)

    @classmethod
    def get_instance(cls) -> MCPLoopRunner:
        with cls._lock:
            if cls._instance is None or not cls._instance._thread.is_alive():
                cls._instance = cls()
            return cls._instance

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_forever()
        finally:
            self._loop.close()

    def run_coro(self, coro: Awaitable[_T], timeout: float | None = None) -> _T:
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result(timeout=timeout)

    def stop(self) -> None:
        if self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)
