import json
import time
from datetime import datetime
from pathlib import Path

import pytest

from logdoctor import analyze
from logdoctor.entries import build_entries
from logdoctor.structured import (
    detect_csv,
    parse_csv_line,
    parse_json_line,
    record_from_mapping,
)

FIXTURES = Path(__file__).parent / "fixtures"


def rec(**fields):
    return record_from_mapping(fields)


def test_common_field_names():
    r = rec(msg="db down", level="error", ts="2024-05-01T10:00:00Z")
    assert (r.message, r.level, r.timestamp) == ("db down", "ERROR", datetime(2024, 5, 1, 10, 0, 0))
    r = rec(message="x", severity="WARNING", time="2024-05-01 10:00:00,250")
    assert (r.level, r.timestamp.microsecond) == ("WARNING", 250000)
    assert rec(event="cache miss", lvl="warn").message == "cache miss"


def test_keys_are_case_insensitive():
    r = rec(Message="x", Level="FATAL")
    assert (r.message, r.level) == ("x", "CRITICAL")


@pytest.mark.parametrize(
    "value, expected",
    [(10, "DEBUG"), (20, "DEBUG"), (30, "INFO"), (40, "WARNING"), (50, "ERROR"), (60, "CRITICAL"), ("50", "ERROR")],
)
def test_pino_numeric_levels(value, expected):
    assert rec(msg="x", level=value).level == expected


def test_epoch_timestamps():
    assert rec(msg="x", time=1714557600).timestamp == datetime(2024, 5, 1, 10, 0, 0)
    assert rec(msg="x", time=1714557600000).timestamp == datetime(2024, 5, 1, 10, 0, 0)
    assert rec(msg="x", time="1714557600").timestamp == datetime(2024, 5, 1, 10, 0, 0)
    assert rec(msg="x", level="info", time=12345).timestamp is None  # not a plausible epoch
    assert rec(msg="x", level="info", time=True).timestamp is None


def test_nested_ecs_style_fields():
    r = record_from_mapping(
        {"@timestamp": "2024-05-01T10:00:00Z", "log": {"level": "error"}, "message": "boom",
         "error": {"type": "PaymentError", "message": "card_declined"}}
    )
    assert r.level == "ERROR" and r.exception_type == "PaymentError" and r.exception_message == "card_declined"


def test_dotted_ecs_keys():
    r = record_from_mapping({"log.level": "warn", "message": "x", "error.type": "T"})
    assert (r.level, r.exception_type) == ("WARNING", "T")


def test_error_string_and_stack_string():
    r = rec(msg="request failed", error="connection refused")
    assert (r.exception_message, r.trace_text, r.level, r.level_inferred) == ("connection refused", None, "ERROR", True)
    r = rec(msg="x", level="error", stack="Error: boom\n    at f (/a.js:1:1)")
    assert r.trace_text.startswith("Error: boom")


def test_explicit_level_is_not_marked_inferred():
    r = rec(msg="x", level="info", error="oops")
    assert (r.level, r.level_inferred) == ("INFO", False)


def test_message_fallbacks():
    assert rec(level="error", error="connection refused").message == "connection refused"
    assert rec(level="error", time="2024-05-01T10:00:00Z").message == "(no message)"
    assert rec(msg=42, level="info").message == "42"
    assert rec(msg=["a"], level="info").message == "(no message)"  # lists are not messages


def test_whitespace_in_message_is_collapsed_and_capped():
    assert rec(msg="a\n  b\t c", level="info").message == "a b c"
    assert len(rec(msg="x" * 5000, level="info").message) == 500


def test_json_that_is_not_a_log_line():
    assert record_from_mapping({"just": "data", "n": 5}) is None
    assert record_from_mapping({}) is None


@pytest.mark.parametrize(
    "line",
    ['{"msg": "cut off", "level": "error"', "[1, 2]", "plain text", '{"msg": "x"} trailing', "", "{" * 20000 + "}" * 20000,
     '{"a":' * 5000 + "1" + "}" * 5000, '{"n": ' + "9" * 6000 + "}"],
)
def test_parse_json_line_rejects_bad_input_without_crashing(line):
    assert parse_json_line(line) is None or parse_json_line(line).message


def test_parse_json_line_needs_line_start():
    assert parse_json_line('  {"msg": "x", "level": "info"}') is None  # indented: a continuation, not a record
    assert parse_json_line('{"msg": "x", "level": "info"}').message == "x"


def test_json_fixture():
    result = analyze((FIXTURES / "json_app.txt").read_text())
    assert result.summary.languages == ["javascript", "python"]
    type_errors = [g for g in result.groups if g.exception_type == "TypeError"]
    assert len(type_errors) == 1 and type_errors[0].count == 2  # different reqId and time, same problem
    assert type_errors[0].frames[-1] == "users.js:getUser"
    payments = [g for g in result.groups if g.exception_type == "PaymentError"]
    assert len(payments) == 1 and payments[0].count == 2
    assert payments[0].title == "payment declined for order 5521"
    assert any(g.language == "python" and g.exception_type == "KeyError" for g in result.groups)
    assert result.summary.first_timestamp == datetime(2024, 5, 1, 10, 0, 0)
    assert result.summary.level_counts["INFO"] == 1


def test_json_title_is_the_message_not_the_raw_line():
    result = analyze('{"level":"error","msg":"db failed","ts":"2024-05-01T10:00:00Z","reqId":"a"}')
    assert result.groups[0].title == "db failed"


def test_repeats_with_different_fields_group_together():
    lines = [
        json.dumps({"level": "error", "msg": "db failed", "ts": f"2024-05-01T10:00:{i:02d}Z", "reqId": f"r{i}", "ms": 100 + i})
        for i in range(5)
    ]
    result = analyze("\n".join(lines))
    assert len(result.groups) == 1 and result.groups[0].count == 5


def test_json_mixed_with_plain_lines():
    text = (
        '{"level":"error","msg":"json problem","ts":"2024-05-01T10:00:00Z"}\n'
        "2024-05-01 10:00:05 ERROR plain problem\n"
        '{"level":"info","msg":"fine","ts":"2024-05-01T10:00:09Z"}\n'
    )
    result = analyze(text)
    assert result.summary.entries == 3
    assert {g.title for g in result.groups} == {"json problem", "plain problem"}


def test_lines_after_a_json_record_stay_with_it():
    text = (
        '{"level":"error","msg":"crashed","ts":"2024-05-01T10:00:00Z"}\n'
        "TypeError: x is undefined\n"
        "    at run (/a/b.js:1:1)\n"
        '{"level":"info","msg":"ok","ts":"2024-05-01T10:00:09Z"}\n'
    )
    entries = build_entries(text.splitlines())
    assert len(entries) == 2
    assert entries[0].language == "javascript" and entries[0].end_line == 3


# ---- CSV ----

def test_detect_csv_delimiters():
    for delimiter in (",", ";", "\t", "|"):
        header = delimiter.join(["time", "level", "message"])
        found = detect_csv([header, "x"])
        assert found and found[1].delimiter == delimiter and found[0] == 0


def test_detect_csv_skips_leading_blank_lines():
    assert detect_csv(["", "", "timestamp,level,message"])[0] == 2


@pytest.mark.parametrize(
    "first_line",
    [
        "2024-05-01 10:00:00 ERROR boom",  # a normal log line
        "name,age,city",  # CSV, but not a log
        "level,count",  # no message column
        "message,notes",  # message but nothing to anchor it as a log
        "timestamp,level,message,1,2",  # numeric column names
        "just one column",
        "Error: something, bad happened",
    ],
)
def test_detect_csv_rejects_other_text(first_line):
    assert detect_csv([first_line, "a,b"]) is None


def test_csv_rows_and_quotes():
    layout = detect_csv(["timestamp,level,message"])[1]
    r = parse_csv_line(layout, '2024-05-01 10:00:00,ERROR,"timeout, retrying"')
    assert (r.message, r.level) == ("timeout, retrying", "ERROR")
    assert parse_csv_line(layout, "garbage without delimiter") is None
    assert parse_csv_line(layout, "") is None
    short = parse_csv_line(layout, "2024-05-01 10:00:00,WARN")  # missing message column
    assert short.level == "WARNING"
    assert short.message == "2024-05-01 10:00:00,WARN"  # the raw row is more useful than a blank


def test_csv_fixture():
    result = analyze((FIXTURES / "csv_app.txt").read_text())
    assert result.summary.entries == 5  # the header row is not a record
    db = [g for g in result.groups if "timed out" in g.title]
    assert len(db) == 1 and db[0].count == 2 and db[0].lines == [3, 4]  # line numbers count the header
    assert result.summary.level_counts == {"CRITICAL": 1, "ERROR": 2, "WARNING": 1, "INFO": 1}


def test_csv_with_unquoted_bad_row_falls_back_to_plain_text():
    text = "timestamp,level,message\nnot a csv row but an ERROR line\n2024-05-01 10:00:00,INFO,fine\n"
    result = analyze(text)
    assert result.summary.entries == 2


# ---- speed and safety ----

def test_fifty_thousand_json_lines_is_fast():
    line = '{"level":"error","msg":"db failed %d","ts":"2024-05-01T10:00:00Z","reqId":"abc","ms":12}'
    text = "\n".join(line % (i % 50) for i in range(50_000))
    start = time.perf_counter()
    result = analyze(text)
    assert time.perf_counter() - start < 5
    assert result.summary.entries == 50_000 and len(result.groups) == 1


def test_fifty_thousand_csv_lines_is_fast():
    text = "timestamp,level,message\n" + "\n".join(
        f"2024-05-01 10:00:00,ERROR,\"db failed {i % 50}, retrying\"" for i in range(50_000)
    )
    start = time.perf_counter()
    result = analyze(text)
    assert time.perf_counter() - start < 5
    assert len(result.groups) == 1


def test_hostile_json_and_csv_lines_are_fast():
    nasty = [
        "{" + '"a":{' * 3000 + "}" * 3000 + "}",
        '{"msg":"' + "\\u0000" * 1500 + '","level":"error"}',
        '{"level":"error","msg":"' + "x" * 9000 + '"}',
        "[" * 9000,
        "timestamp,level,message\n" + '"' * 9000,
        "timestamp,level,message\n" + "," * 9000,
    ]
    start = time.perf_counter()
    for text in nasty:
        analyze(text)
    assert time.perf_counter() - start < 3
