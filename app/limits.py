"""Protection for a small free server: size caps and a concurrency gate."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any, TypeVar

from fastapi import Request
from starlette.concurrency import run_in_threadpool

from app.errors import ApiError

T = TypeVar("T")


def format_bytes(count: int) -> str:
    if count >= 1024 * 1024:
        value = count / (1024 * 1024)
        return f"{value:g} MB" if value == int(value) else f"{value:.1f} MB"
    if count >= 1024:
        return f"{count // 1024} KB"
    return f"{count} bytes"


def too_large(limit: int, hint: str = "") -> ApiError:
    message = f"This is larger than the {format_bytes(limit)} limit."
    if hint:
        message = f"{message} {hint}"
    return ApiError(413, "payload_too_large", message)


async def read_limited_body(request: Request, max_bytes: int, hint: str = "") -> bytes:
    """Read the request body, refusing to hold more than `max_bytes`.

    The body is read in chunks and counted, so an oversized or endless upload
    is cut off early instead of being loaded into memory first.
    """
    declared = request.headers.get("content-length")
    if declared is not None:
        try:
            size = int(declared)
        except ValueError:
            raise ApiError(400, "bad_request", "The Content-Length header is not a number.") from None
        if size > max_bytes:
            raise too_large(max_bytes, hint)

    chunks: list[bytes] = []
    total = 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > max_bytes:
            raise too_large(max_bytes, hint)
        chunks.append(chunk)
    return b"".join(chunks)


class AnalysisGate:
    """Lets only a few analyses run at once and turns the rest away politely.

    Analysis uses CPU. On a small free server it is better to say "busy,
    try again" than to let requests pile up until everything is slow.
    """

    def __init__(self, limit: int):
        self._slots = asyncio.Semaphore(limit)

    async def run(self, function: Callable[..., T], *args: Any, **kwargs: Any) -> T:
        if self._slots.locked():
            raise ApiError(
                503,
                "server_busy",
                "The server is busy analyzing other logs. Please try again in a few seconds.",
                headers={"Retry-After": "5"},
            )
        async with self._slots:
            return await run_in_threadpool(function, *args, **kwargs)
