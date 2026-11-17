from datetime import datetime, timedelta

from logdoctor.models import LogEntry
from logdoctor.timeline import build_timeline

BASE = datetime(2026, 11, 18, 1, 0, 0)


def entry(seconds, level="ERROR"):
    return LogEntry(
        line=1,
        end_line=1,
        timestamp=BASE + timedelta(seconds=seconds) if seconds is not None else None,
        level=level,
        level_inferred=False,
        message="m",
        text="m",
    )


def test_no_timestamps():
    timeline = build_timeline([entry(None), entry(None)])
    assert timeline.has_timestamps is False
    assert timeline.buckets == []
    assert timeline.bucket_seconds is None


def test_timestamps_but_no_failures():
    timeline = build_timeline([entry(0, "INFO"), entry(5, "DEBUG")])
    assert timeline.has_timestamps is True
    assert timeline.buckets == []


def test_single_failure_is_one_bucket():
    timeline = build_timeline([entry(0)])
    assert timeline.bucket_seconds == 1
    assert [(b.errors, b.warnings) for b in timeline.buckets] == [(1, 0)]


def test_errors_and_warnings_are_counted_separately():
    timeline = build_timeline([entry(0), entry(1, "CRITICAL"), entry(2, "WARNING"), entry(3, "INFO")])
    assert sum(b.errors for b in timeline.buckets) == 2
    assert sum(b.warnings for b in timeline.buckets) == 1


def test_bucket_size_grows_with_the_time_span():
    short = build_timeline([entry(0), entry(30)])  # 30 seconds
    hour = build_timeline([entry(0), entry(3600)])  # 1 hour
    week = build_timeline([entry(0), entry(7 * 86400)])  # 1 week
    assert short.bucket_seconds == 1
    assert hour.bucket_seconds == 300  # 1-minute buckets would be 61, over the target of 60
    assert week.bucket_seconds == 21600
    for timeline in (short, hour, week):
        assert len(timeline.buckets) <= 60


def test_empty_buckets_are_filled_in_between_events():
    timeline = build_timeline([entry(0), entry(600)])  # 10 minutes apart
    counts = [b.errors for b in timeline.buckets]
    assert counts[0] == 1 and counts[-1] == 1
    assert sum(counts) == 2
    assert 0 in counts  # a gap shows as zeros, not as a missing bar


def test_buckets_are_in_order_and_evenly_spaced():
    timeline = build_timeline([entry(0), entry(250), entry(1000)])
    starts = [b.start for b in timeline.buckets]
    assert starts == sorted(starts)
    gaps = {(b - a).total_seconds() for a, b in zip(starts, starts[1:])}
    assert gaps == {timeline.bucket_seconds}


def test_huge_time_span_stays_small():
    far = [entry(0), entry(86400 * 365 * 3000)]  # logs 3000 years apart
    timeline = build_timeline(far)
    assert len(timeline.buckets) <= 500
    assert sum(b.errors for b in timeline.buckets) == 2
