import time
from pathlib import Path

from logdoctor import analyze
from logdoctor.entries import build_entries
from logdoctor.nodetrace import detect_node, looks_like_js_exception, parse_frame

FIXTURE = Path(__file__).parent / "fixtures" / "node_app.txt"


def test_parse_frame_shapes():
    assert parse_frame("    at getUser (/app/src/users.js:42:17)") == "users.js:getUser"
    assert parse_frame("    at /app/src/server.js:10:5") == "server.js:<anonymous>"
    assert parse_frame("    at async Promise.all (index 0)") == "<native>:Promise.all"
    assert parse_frame("    at new Foo (/a/foo.js:1:2)") == "foo.js:Foo"
    assert parse_frame("    at Layer.handle [as handle_request] (/a/layer.js:9:9)") == "layer.js:Layer.handle"
    assert parse_frame("    at node:internal/process/task_queues:96:5") == "task_queues:<anonymous>"
    assert parse_frame(r"    at run (C:\app\src\main.js:3:4)") == "main.js:run"
    assert parse_frame("    at file:///app/x.mjs:5:6") == "x.mjs:<anonymous>"
    assert parse_frame("    at eval (eval at <anonymous> (/a/b.js:1:1), <anonymous>:1:1)") == "<eval>:eval"


def test_parse_frame_rejects_other_languages_and_text():
    assert parse_frame("\tat com.acme.Foo.bar(Foo.java:42)") is None  # Java
    assert parse_frame('  File "/a/b.py", line 3, in run') is None  # Python
    assert parse_frame("    at the end of the day we shipped") is None
    assert parse_frame("at /a/b.js:1:2") is None  # not indented: just prose
    assert parse_frame("") is None


def test_simple_error():
    result = detect_node(
        "TypeError: Cannot read properties of undefined (reading 'id')\n"
        "    at getUser (/app/users.js:42:17)\n"
        "    at /app/server.js:10:5"
    )
    assert result.exception_type == "TypeError"
    assert result.exception_message == "Cannot read properties of undefined (reading 'id')"
    assert result.frames == ["server.js:<anonymous>", "users.js:getUser"]  # innermost last


def test_error_code_in_brackets_and_uncaught_prefix():
    result = detect_node("Uncaught AssertionError [ERR_ASSERTION]: nope\n    at a (/x/y.js:1:1)")
    assert result.exception_type == "AssertionError"
    assert result.exception_message == "nope"


def test_cause_is_the_root():
    result = detect_node(
        "Error: query failed\n"
        "    at runQuery (/a/db.js:77:11)\n"
        "    [cause]: MongoServerError: ECONNREFUSED\n"
        "        at onError (/a/conn.js:2:3)"
    )
    assert result.exception_type == "MongoServerError"
    assert result.frames == ["conn.js:onError"]


def test_custom_name_needs_a_frame():
    assert detect_node("ValidationFailed: bad\n    at a (/x.js:1:1)").exception_type == "ValidationFailed"
    assert detect_node("ValidationFailed: bad") is None


def test_no_trace_means_none():
    assert detect_node("everything is fine") is None
    assert detect_node("Error: mentioned but no frames") is None
    assert detect_node("    at a (/x.js:1:1)") is None


def test_looks_like_js_exception_needs_next_frame():
    frame = "    at a (/x.js:1:1)"
    assert looks_like_js_exception("Error: boom", frame)
    assert not looks_like_js_exception("Error: boom", "something else")
    assert not looks_like_js_exception("Error: boom", None)
    assert not looks_like_js_exception("    Error: boom", frame)


def test_fixture_groups_repeated_type_error():
    result = analyze(FIXTURE.read_text())
    assert result.summary.languages == ["javascript"]
    type_errors = [g for g in result.groups if g.exception_type == "TypeError"]
    assert len(type_errors) == 1 and type_errors[0].count == 2
    assert any(g.exception_type == "MongoServerError" for g in result.groups)
    assert result.summary.level_counts["INFO"] == 1
    assert result.summary.level_counts["WARNING"] == 1  # lowercase "warn:" is read


def test_consecutive_plain_error_lines_do_not_merge():
    # Plain CLI-style output: without a following stack frame, each line is its own record.
    text = "Error: first thing failed\nError: second thing failed\nError: third thing failed\n"
    assert len(build_entries(text.splitlines())) == 3
    # An exception line that has stack frames joins the error line before it.
    # That is the "ERROR request failed" + "TypeError: ..." pattern, and it cannot
    # be told apart from this case.
    with_trace = text + "    at run (/a/b.js:1:1)\n"
    entries = build_entries(with_trace.splitlines())
    assert len(entries) == 2
    assert entries[1].exception_message == "third thing failed"


def test_untimestamped_error_line_keeps_its_trace():
    text = "ERROR request failed\nTypeError: x is undefined\n    at a (/x.js:1:1)\nINFO ok\n"
    entries = build_entries(text.splitlines())
    assert entries[0].language == "javascript"
    assert entries[0].end_line == 3


def test_java_and_python_are_not_taken_for_javascript():
    java = analyze("2024-05-01 10:00:00 ERROR x\njava.lang.Error: x\n\tat a.B.c(B.java:1)\n")
    assert java.summary.languages == ["java"]
    py = analyze('2024-05-01 10:00:00 ERROR x\nTraceback (most recent call last):\n  File "a.py", line 1, in f\nKeyError: 1\n')
    assert py.summary.languages == ["python"]


def test_hostile_input_is_fast():
    nasty = [
        "    at " + "(" * 50000,
        "    at " + "a (" * 20000,
        "Error: " + "x" * 100000,
        "    at f (" + "/a" * 30000 + ":1:2)",
        "[cause]: " * 5000,
    ]
    start = time.perf_counter()
    for line in nasty:
        detect_node(line + "\n" + line)
        looks_like_js_exception(line, line)
    assert time.perf_counter() - start < 1.0
