
from __future__ import annotations

import threading
from datetime import UTC, datetime

from pydantic import BaseModel


class MCPMetricsSnapshot(BaseModel):
    server_name: str
    total_executions: int
    total_failures: int
    active_requests: int
    last_execution_at: datetime | None
    connected_since: datetime | None


class _ServerMetrics:
    __slots__ = (
        "total_executions",
        "total_failures",
        "active_requests",
        "last_execution_at",
        "connected_since",
    )

    def __init__(self) -> None:
        self.total_executions = 0
        self.total_failures = 0
        self.active_requests = 0
        self.last_execution_at: datetime | None = None
        self.connected_since: datetime | None = None


class MCPMetricsCollector:

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._servers: dict[str, _ServerMetrics] = {}

    def _get(self, server_name: str) -> _ServerMetrics:
        metrics = self._servers.get(server_name)

        if metrics is None:
            metrics = _ServerMetrics()
            self._servers[server_name] = metrics

        return metrics

    def record_start(self, server_name: str) -> None:
        with self._lock:
            self._get(server_name).active_requests += 1

    def record_success(self, server_name: str) -> None:
        with self._lock:
            metrics = self._get(server_name)
            metrics.active_requests = max(0, metrics.active_requests - 1)
            metrics.total_executions += 1
            metrics.last_execution_at = datetime.now(UTC)

    def record_failure(self, server_name: str) -> None:
        with self._lock:
            metrics = self._get(server_name)
            metrics.active_requests = max(0, metrics.active_requests - 1)
            metrics.total_executions += 1
            metrics.total_failures += 1
            metrics.last_execution_at = datetime.now(UTC)

    def record_connected(self, server_name: str) -> None:
        with self._lock:
            metrics = self._get(server_name)

            if metrics.connected_since is None:
                metrics.connected_since = datetime.now(UTC)

    def snapshot(self, server_name: str) -> MCPMetricsSnapshot:
        with self._lock:
            metrics = self._get(server_name)

            return MCPMetricsSnapshot(
                server_name=server_name,
                total_executions=metrics.total_executions,
                total_failures=metrics.total_failures,
                active_requests=metrics.active_requests,
                last_execution_at=metrics.last_execution_at,
                connected_since=metrics.connected_since,
            )

    def all_snapshots(self) -> list[MCPMetricsSnapshot]:
        with self._lock:
            server_names = list(self._servers.keys())

        return [self.snapshot(name) for name in server_names]
