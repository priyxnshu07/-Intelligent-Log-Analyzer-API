import json
from pathlib import Path

from logdoctor import analyze

FIXTURE = Path(__file__).parent / "fixtures" / "python_app.txt"


def load():
    return analyze(FIXTURE.read_text())


def test_summary_of_the_sample_log():
    summary = load().summary
    assert summary.total_lines == 30
    assert summary.lines_analyzed == 30
    assert summary.truncated is False
    assert summary.entries == 9
    assert summary.level_counts == {"CRITICAL": 1, "ERROR": 5, "WARNING": 1, "INFO": 2}
    assert summary.error_count == 6
    assert summary.warning_count == 1
    assert summary.group_count == 5
    assert summary.languages == ["python"]
    assert str(summary.first_timestamp).startswith("2026-11-18 01:00:00")
    assert str(summary.last_timestamp) == "2026-11-18 01:03:05"


def test_repeated_errors_are_grouped_with_evidence_line_numbers():
    groups = {g.title: g for g in load().groups}
    keyerror = groups["KeyError: 'user_id'"]
    assert keyerror.count == 2
    assert keyerror.lines == [3, 9]
    assert keyerror.frames == ["views.py:get_user"]
    assert keyerror.language == "python"
    assert keyerror.sample.startswith("2026-11-18 01:00:06")

    connect = next(g for g in load().groups if "could not connect" in g.title)
    assert connect.count == 2
    assert connect.pattern == "app.db could not connect to <ip> after <n> retries"
    assert connect.lines == [14, 15]


def test_groups_are_sorted_by_severity_then_frequency():
    groups = load().groups
    levels = [g.level for g in groups]
    assert levels == ["CRITICAL", "ERROR", "ERROR", "ERROR", "WARNING"]
    errors = [g for g in groups if g.level == "ERROR"]
    assert [g.count for g in errors] == sorted((g.count for g in errors), reverse=True)


def test_timeline_for_the_sample_log():
    timeline = load().timeline
    assert timeline.has_timestamps is True
    assert timeline.bucket_seconds == 10
    assert sum(b.errors for b in timeline.buckets) == 6
    assert sum(b.warnings for b in timeline.buckets) == 1


def test_result_can_be_turned_into_json():
    data = load().to_dict()
    text = json.dumps(data)
    assert json.loads(text)["summary"]["group_count"] == 5
    assert data["summary"]["first_timestamp"].startswith("2026-11-18T01:00:00")
    assert load().to_json().startswith("{")


def test_empty_and_blank_input():
    for text in ("", "\n\n", "   \n\t\n"):
        result = analyze(text)
        assert result.summary.entries == 0
        assert result.groups == []
        assert result.timeline.buckets == []
        assert result.summary.truncated is False


def test_windows_line_endings_and_no_trailing_newline():
    text = "2026-11-18 01:00:00 ERROR a\r\n2026-11-18 01:00:01 ERROR a"
    result = analyze(text)
    assert result.summary.total_lines == 2
    assert result.groups[0].count == 2


def test_only_the_most_recent_lines_are_analyzed_when_over_the_limit():
    text = "\n".join(f"2026-11-18 01:00:{i % 60:02d} ERROR failure number {i}" for i in range(100))
    result = analyze(text, max_lines=10)
    summary = result.summary
    assert summary.total_lines == 100
    assert summary.lines_analyzed == 10
    assert summary.truncated is True
    assert summary.entries == 10
    group = result.groups[0]
    assert group.count == 10
    assert group.first_line == 91  # line numbers still refer to the original input
    assert group.last_line == 100


def test_exactly_at_the_limit_is_not_truncated():
    text = "\n".join(f"2026-11-18 01:00:00 INFO line {i}" for i in range(10))
    assert analyze(text, max_lines=10).summary.truncated is False


def test_evidence_lines_are_capped_but_count_is_exact():
    text = "\n".join("2026-11-18 01:00:00 ERROR same problem" for _ in range(500))
    group = analyze(text).groups[0]
    assert group.count == 500
    assert len(group.lines) == 20


def test_a_warning_and_an_error_with_the_same_message_share_one_group_at_the_higher_level():
    text = "2026-11-18 01:00:00 WARN disk full\n2026-11-18 01:00:01 ERROR disk full"
    groups = analyze(text).groups
    assert len(groups) == 1
    assert groups[0].level == "ERROR"
    assert groups[0].count == 2


def test_info_and_debug_lines_are_counted_but_not_grouped():
    text = "2026-11-18 01:00:00 INFO a\n2026-11-18 01:00:01 DEBUG b"
    result = analyze(text)
    assert result.summary.entries == 2
    assert result.groups == []


def test_plain_text_log_without_levels_still_finds_failures():
    text = "starting\nConnectionError: refused by server\nfinished"
    result = analyze(text)
    assert result.summary.error_count == 1
    assert result.groups[0].exception_type == "ConnectionError"
    assert result.timeline.has_timestamps is False
