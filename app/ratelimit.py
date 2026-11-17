"""Per-visitor request limits, kept in memory only.

A visitor is identified by IP address. Nothing is written to disk and nothing
is shared between server restarts, which matches the stateless design. The
counters are small timestamps, forgotten after a minute.
"""

from __future__ import annotations

import math
import time
from collections import deque
from collections.abc import Callable

from fastapi import Request

from app.errors import ApiError

WINDOW_SECONDS = 60.0
MAX_TRACKED_VISITORS = 10_000


def client_ip(request: Request, trust_proxy: bool) -> str:
    """The visitor's address. Behind Render's proxy it comes from X-Forwarded-For.

    Only the last entry is used: that one was added by the trusted proxy,
    while earlier entries can be written by the visitor.
    """
    if trust_proxy:
        forwarded = request.headers.get("x-forwarded-for", "")
        last = forwarded.split(",")[-1].strip()
        if last:
            return last[:64]
    return request.client.host if request.client else "unknown"


class RateLimiter:
    """Sliding window: at most `limit` requests per visitor in the last minute."""

    def __init__(self, limit: int, clock: Callable[[], float] = time.monotonic):
        self.limit = limit
        self._clock = clock
        self._seen: dict[str, deque[float]] = {}

    def check(self, visitor: str) -> int | None:
        """Count this request. Returns None if allowed, else seconds to wait."""
        now = self._clock()
        cutoff = now - WINDOW_SECONDS
        window = self._seen.get(visitor)
        if window is None:
            if len(self._seen) >= MAX_TRACKED_VISITORS:
                self._forget_old(cutoff)
            window = self._seen.setdefault(visitor, deque())
        while window and window[0] <= cutoff:
            window.popleft()
        if len(window) >= self.limit:
            return max(1, math.ceil(window[0] + WINDOW_SECONDS - now))
        window.append(now)
        return None

    def _forget_old(self, cutoff: float) -> None:
        for visitor in [v for v, w in self._seen.items() if not w or w[-1] <= cutoff]:
            del self._seen[visitor]
        while len(self._seen) >= MAX_TRACKED_VISITORS:  # still full: drop the oldest visitor
            del self._seen[next(iter(self._seen))]


def limit_dependency(name: str):
    """A FastAPI dependency that applies the limiter stored at app.state.<name>."""

    async def check(request: Request) -> None:
        limiter: RateLimiter = getattr(request.app.state, name)
        wait = limiter.check(client_ip(request, request.app.state.settings.trust_proxy))
        if wait is not None:
            raise ApiError(
                429,
                "rate_limited",
                f"Too many requests. Please wait {wait} seconds and try again.",
                headers={"Retry-After": str(wait)},
            )

    return check
