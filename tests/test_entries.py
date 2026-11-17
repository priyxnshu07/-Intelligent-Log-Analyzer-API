from logdoctor.entries import build_entries


def lines(text):
    return text.strip("\n").split("\n")


def test_traceback_stays_with_the_error_line_that_logged_it():
    entries = build_entries(
        lines(
            """
2026-11-18 01:00:00 INFO app starting
2026-11-18 01:00:01 ERROR app Request failed
Traceback (most recent call last):
  File "/srv/app/views.py", line 42, in get_user
    name = data["user_id"]
KeyError: 'user_id'
2026-11-18 01:00:02 INFO app done
"""
        )
    )
    assert [e.level for e in entries] == ["INFO", "ERROR", "INFO"]
    error = entries[1]
    assert error.message == "app Request failed"
    assert error.language == "python"
    assert error.exception_type == "KeyError"
    assert error.exception_message == "'user_id'"
    assert error.frames == ["views.py:get_user"]
    assert (error.line, error.end_line) == (2, 6)


def test_bare_traceback_after_info_line_becomes_its_own_error():
    entries = build_entries(
        lines(
            """
2026-11-18 01:00:00 INFO app starting job
Traceback (most recent call last):
  File "a.py", line 3, in <module>
    1/0
ZeroDivisionError: division by zero
2026-11-18 01:00:01 INFO app next
"""
        )
    )
    assert [e.level for e in entries] == ["INFO", "ERROR", "INFO"]
    assert entries[1].level_inferred is True
    assert entries[1].exception_type == "ZeroDivisionError"


def test_pasted_traceback_without_timestamps_is_one_record():
    entries = build_entries(
        lines(
            """
Traceback (most recent call last):
  File "a.py", line 3, in <module>
    1/0
ZeroDivisionError: division by zero
"""
        )
    )
    assert len(entries) == 1
    assert entries[0].level == "ERROR"
    assert entries[0].exception_type == "ZeroDivisionError"


def test_chained_exceptions_are_one_record_using_the_final_exception():
    entries = build_entries(
        lines(
            """
2026-11-18 01:00:00 ERROR app job failed
Traceback (most recent call last):
  File "jobs.py", line 20, in helper
    return int(x)
ValueError: invalid literal

During handling of the above exception, another exception occurred:

Traceback (most recent call last):
  File "jobs.py", line 30, in run_safe
    raise RuntimeError("job crashed")
RuntimeError: job crashed
2026-11-18 01:00:05 INFO app next
"""
        )
    )
    assert len(entries) == 2
    assert entries[0].exception_type == "RuntimeError"
    assert entries[0].frames == ["jobs.py:run_safe"]
    assert "ValueError" in entries[0].text  # the cause is still in the sample


def test_chained_exceptions_without_timestamps_are_one_record():
    entries = build_entries(
        lines(
            """
Traceback (most recent call last):
  File "a.py", line 1, in f
ValueError: first

The above exception was the direct cause of the following exception:

Traceback (most recent call last):
  File "a.py", line 5, in g
RuntimeError: second
"""
        )
    )
    assert len(entries) == 1
    assert entries[0].exception_type == "RuntimeError"


def test_indented_java_style_lines_stay_with_their_record():
    entries = build_entries(
        lines(
            """
2026-11-18 01:00:00 ERROR [main] Unable to start
java.lang.NullPointerException: boom
\tat com.example.Foo.bar(Foo.java:10)
\tat com.example.Main.main(Main.java:5)
2026-11-18 01:00:01 INFO [main] retrying
"""
        )
    )
    assert len(entries) == 2
    assert entries[0].end_line == 4
    assert entries[0].exception_type is None  # the Java detector arrives in a later step


def test_plain_text_gives_one_record_per_line_and_infers_failures():
    entries = build_entries(
        lines(
            """
starting worker
connection refused: ValueError raised in handler
all done
"""
        )
    )
    assert len(entries) == 3
    assert [e.level for e in entries] == ["UNKNOWN", "ERROR", "UNKNOWN"]
    assert entries[1].level_inferred is True
    assert entries[1].exception_type == "ValueError"


def test_explicit_level_is_never_overridden_by_failure_words():
    entries = build_entries(lines("2026-11-18 01:00:00 INFO retried after an error, all good"))
    assert entries[0].level == "INFO"
    assert entries[0].level_inferred is False


def test_blank_lines_are_skipped_and_line_numbers_use_the_offset():
    entries = build_entries(
        ["", "2026-11-18 01:00:00 ERROR a", "", "2026-11-18 01:00:01 ERROR b"],
        first_line_no=101,
    )
    assert [e.line for e in entries] == [102, 104]


def test_empty_input():
    assert build_entries([]) == []
    assert build_entries(["", "   ", "\t"]) == []


def test_only_continuation_lines_still_make_a_record():
    entries = build_entries(["    orphan indented line"])
    assert len(entries) == 1
    assert entries[0].message == "orphan indented line"


def test_very_long_record_is_shortened_but_keeps_the_final_error():
    body = [f'  File "m.py", line {i}, in f{i}' for i in range(500)]
    text = (
        "2026-11-18 01:00:00 ERROR crash\nTraceback (most recent call last):\n"
        + "\n".join(body)
        + "\nRecursionError: maximum recursion depth exceeded"
    )
    entry = build_entries(text.split("\n"))[0]
    assert entry.exception_type == "RecursionError"
    assert len(entry.text) < 4100
    assert "[truncated]" in entry.text
    assert entry.text.endswith("RecursionError: maximum recursion depth exceeded")
