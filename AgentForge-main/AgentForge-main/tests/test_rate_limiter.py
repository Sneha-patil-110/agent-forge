from __future__ import annotations

from backend.services.rate_limiter import RateLimiter


def test_check_allows_hits_up_to_the_limit() -> None:
    limiter = RateLimiter()

    results = [limiter.check("key", limit=3, window_seconds=60.0) for _ in range(3)]

    assert results == [True, True, True]


def test_check_rejects_hits_beyond_the_limit() -> None:
    limiter = RateLimiter()

    for _ in range(3):
        limiter.check("key", limit=3, window_seconds=60.0)

    assert limiter.check("key", limit=3, window_seconds=60.0) is False


def test_check_is_scoped_per_key() -> None:
    limiter = RateLimiter()

    for _ in range(3):
        limiter.check("key-one", limit=3, window_seconds=60.0)

    assert limiter.check("key-two", limit=3, window_seconds=60.0) is True


def test_check_expires_old_hits_outside_the_window() -> None:
    limiter = RateLimiter()

    for _ in range(3):
        limiter.check("key", limit=3, window_seconds=0.05)

    assert limiter.check("key", limit=3, window_seconds=0.05) is False

    import time

    time.sleep(0.1)

    assert limiter.check("key", limit=3, window_seconds=0.05) is True
