"""Count failures over time."""

from __future__ import annotations

from datetime import datetime, timedelta

from logdoctor.levels import ERROR_RANK, WARNING_RANK, rank
from logdoctor.models import LogEntry, Timeline, TimelineBucket

# Bucket sizes in seconds: 1s, 10s, 1min, 5min, 15min, 1h, 6h, 1 day, 1 week.
_LADDER = (1, 10, 60, 300, 900, 3600, 21600, 86400, 604800)
_TARGET_BUCKETS = 60
_MAX_FILLED_BUCKETS = 500  # beyond this only buckets that have events are returned
_EPOCH = datetime(1970, 1, 1)


def build_timeline(entries: list[LogEntry]) -> Timeline:
    has_timestamps = any(entry.timestamp for entry in entries)
    if not has_timestamps:
        return Timeline(None, False, [])

    points = [
        (entry.timestamp, rank(entry.level) >= ERROR_RANK)
        for entry in entries
        if entry.timestamp and rank(entry.level) >= WARNING_RANK
    ]
    if not points:
        return Timeline(None, True, [])

    seconds = [(moment - _EPOCH).total_seconds() for moment, _ in points]
    span = max(seconds) - min(seconds)
    size = next((s for s in _LADDER if span // s + 1 <= _TARGET_BUCKETS), _LADDER[-1])

    counts: dict[int, list[int]] = {}
    for (moment, is_error), second in zip(points, seconds):
        start = int(second // size) * size
        bucket = counts.setdefault(start, [0, 0])
        bucket[0 if is_error else 1] += 1

    first, last = min(counts), max(counts)
    if (last - first) // size + 1 <= _MAX_FILLED_BUCKETS:
        starts = range(first, last + size, size)
    else:
        starts = sorted(counts)

    buckets = [
        TimelineBucket(
            start=_EPOCH + timedelta(seconds=start),
            errors=counts.get(start, [0, 0])[0],
            warnings=counts.get(start, [0, 0])[1],
        )
        for start in starts
    ]
    return Timeline(size, True, buckets)
