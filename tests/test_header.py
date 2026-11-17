from datetime import datetime

import pytest

from logdoctor.header import parse_header


@pytest.mark.parametrize(
    "line, level, message_part",
    [
        ("2026-11-18 01:00:00,123 INFO app.main Starting", "INFO", "app.main Starting"),
        ("2026-11-18T01:00:00Z ERROR something broke", "ERROR", "something broke"),
        ("[2026-11-18 01:00:00] [WARN] disk almost full", "WARNING", "disk almost full"),
        ("ERROR [main] Unable to start", "ERROR", "Unable to start"),
        ("INFO[0000] server started", "INFO", "server started"),
        ("ERRO[0001] connection refused", "ERROR", "connection refused"),
        ("error: something failed", "ERROR", "something failed"),
        ("Error: connect ECONNREFUSED 127.0.0.1:5432", "ERROR", "connect ECONNREFUSED"),
        ("FATAL: out of memory", "CRITICAL", "out of memory"),
        ("SEVERE: java logging style", "ERROR", "java logging style"),
        ("2026-11-18 01:00:00 DEBUG cache miss", "DEBUG", "cache miss"),
        ('{"level":"error","msg":"boom"}', "ERROR", "boom"),
        ("level=warn msg=slow", "WARNING", "slow"),
        ("just a plain line", "UNKNOWN", "just a plain line"),
        ("NOERROR in the middle", "UNKNOWN", "NOERROR"),
        ("ERR_CONNECTION_REFUSED while loading", "UNKNOWN", "ERR_CONNECTION_REFUSED"),
        ("Starting INFORMATION service", "UNKNOWN", "INFORMATION"),
    ],
)
def test_level_and_message(line, level, message_part):
    header = parse_header(line)
    assert header is not None
    assert header.level == level
    assert message_part in header.message


def test_timestamp_inside_json_or_key_value_lines_is_not_cut_out_of_the_message():
    json_line = '{"level":"error","time":"2026-11-18T02:01:00Z","msg":"payment declined"}'
    header = parse_header(json_line)
    assert header.message == json_line
    assert header.timestamp == datetime(2026, 11, 18, 2, 1, 0)

    kv = 'time="2026-11-18T02:02:00Z" level=error msg="dial tcp refused"'
    assert parse_header(kv).message == kv
    assert parse_header(kv).level == "ERROR"


def test_message_keeps_leading_brackets_that_are_not_timestamps():
    header = parse_header("2026-11-18 01:00:00 ERROR [db] connection lost")
    assert header.message == "[db] connection lost"


@pytest.mark.parametrize(
    "line, expected",
    [
        ("2026-11-18T05:30:00+05:30 INFO x", datetime(2026, 11, 18, 0, 0, 0)),
        ("2026-11-18T01:00:00-05:00 INFO x", datetime(2026, 11, 18, 6, 0, 0)),
        ("2026-11-18T01:00:00+0000 INFO x", datetime(2026, 11, 18, 1, 0, 0)),
        ("2026-11-18T01:00:00Z INFO x", datetime(2026, 11, 18, 1, 0, 0)),
        ("2026-11-18 01:00:00,250 INFO x", datetime(2026, 11, 18, 1, 0, 0, 250000)),
        ("2026-11-18 01:00:00.5 INFO x", datetime(2026, 11, 18, 1, 0, 0, 500000)),
        ("2026-11-18 01:00:00 INFO x", datetime(2026, 11, 18, 1, 0, 0)),
    ],
)
def test_timestamps_become_naive_utc(line, expected):
    assert parse_header(line).timestamp == expected


@pytest.mark.parametrize(
    "line",
    ["2026-13-45 99:99:99 INFO x", "no timestamp here", "12:00:00 INFO only a time"],
)
def test_invalid_or_missing_timestamp_is_none(line):
    assert parse_header(line).timestamp is None


def test_indented_and_blank_lines_have_no_header():
    assert parse_header("    at com.example.Foo.bar(Foo.java:10)") is None
    assert parse_header("\tat something") is None
    assert parse_header("") is None


def test_strong_marks_lines_that_start_a_record():
    assert parse_header("2026-11-18 01:00:00 hello").strong
    assert parse_header("[ERROR] hello").strong
    assert parse_header('{"msg": "x"}').strong
    assert not parse_header("plain continuation text").strong
    # a level word far from the start of a long line does not count
    assert not parse_header("x" * 100 + " ERROR here").strong
