
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque


class RateLimiter:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str, *, limit: int, window_seconds: float = 60.0) -> bool:

        now = time.monotonic()
        cutoff = now - window_seconds

        with self._lock:
            hits = self._hits[key]

            while hits and hits[0] < cutoff:
                hits.popleft()

            if len(hits) >= limit:
                return False

            hits.append(now)
            return True
