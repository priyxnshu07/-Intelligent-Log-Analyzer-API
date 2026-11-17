import time
from pathlib import Path

from logdoctor import analyze
from logdoctor.entries import build_entries
from logdoctor.javatrace import detect_java, looks_like_java_exception

FIXTURE = Path(__file__).parent / "fixtures" / "java_app.txt"


def trace(text):
    return detect_java(text.strip("\n").replace("    ", "\t"))


def test_simple_exception():
    result = trace(
        """
java.lang.NullPointerException: name is null
    at com.acme.Util.clean(Util.java:12)
    at com.acme.App.main(App.java:30)
"""
    )
    assert result.exception_type == "java.lang.NullPointerException"
    assert result.exception_message == "name is null"
    assert result.frames == ["App.java:App.main", "Util.java:Util.clean"]  # innermost last


def test_root_cause_is_reported():
    result = trace(
        """
java.lang.RuntimeException: wrapper
    at a.B.c(B.java:1)
Caused by: java.io.IOException: disk full
    at a.D.e(D.java:2)
    ... 3 more
"""
    )
    assert result.exception_type == "java.io.IOException"
    assert result.exception_message == "disk full"
    assert result.frames == ["D.java:D.e"]


def test_suppressed_section_is_not_the_failure():
    result = trace(
        """
java.lang.IllegalStateException: main failure
    at a.B.c(B.java:1)
    Suppressed: java.io.IOException: close failed
        at a.X.close(X.java:9)
"""
    )
    assert result.exception_type == "java.lang.IllegalStateException"
    assert result.frames == ["B.java:B.c"]


def test_uncaught_in_thread_and_module_prefix():
    result = trace(
        """
Exception in thread "main" java.lang.OutOfMemoryError: Java heap space
    at java.base/java.util.Arrays.copyOf(Arrays.java:3512)
    at app.Main.main(Main.java:7)
"""
    )
    assert result.exception_type == "java.lang.OutOfMemoryError"
    assert result.frames[-1] == "Arrays.java:Arrays.copyOf"


def test_native_method_frame_uses_class_name():
    result = trace(
        """
java.lang.Error: x
    at sun.misc.Unsafe.park(Native Method)
"""
    )
    assert result.frames == ["Unsafe:Unsafe.park"]


def test_custom_exception_name_needs_frames():
    text = "com.acme.ValidationFailed: bad\n\tat com.acme.A.b(A.java:1)"
    assert detect_java(text).exception_type == "com.acme.ValidationFailed"
    assert detect_java("com.acme.ValidationFailed: bad") is None


def test_no_trace_means_none():
    assert detect_java("just a normal log line") is None
    assert detect_java("java.lang.Exception: mentioned but no frames") is None
    assert detect_java("\tat not a frame") is None


def test_looks_like_java_exception():
    assert looks_like_java_exception("java.lang.NullPointerException: x")
    assert looks_like_java_exception("Caused by: foo.Bar: x")
    assert looks_like_java_exception('Exception in thread "main" java.lang.Error: x')
    assert not looks_like_java_exception("Exception: plain python-style")  # no package
    assert not looks_like_java_exception("Connection refused")
    assert not looks_like_java_exception("\tat a.B.c(B.java:1)")


def test_frames_capped_to_innermost_ten():
    frames = "\n".join(f"\tat a.C{i}.m(C{i}.java:{i})" for i in range(40))
    result = detect_java("java.lang.Exception: deep\n" + frames)
    assert len(result.frames) == 10
    assert result.frames[-1] == "C0.java:C0.m"  # innermost call is first in Java output


def test_fixture_groups_by_root_cause():
    result = analyze(FIXTURE.read_text())
    assert result.summary.languages == ["java"]
    timeouts = [g for g in result.groups if "SQLTransientConnectionException" in (g.exception_type or "")]
    assert len(timeouts) == 1 and timeouts[0].count == 2  # 30000ms and 30001ms are the same problem
    npe = [g for g in result.groups if g.exception_type == "java.lang.NullPointerException"]
    assert len(npe) == 1 and npe[0].frames[-1] == "Util.java:Util.clean"
    assert any(g.level == "WARNING" and g.language is None for g in result.groups)


def test_trace_without_timestamps_stays_attached_to_error_line():
    text = (
        "ERROR Failed to place order\n"
        "java.lang.IllegalStateException: boom\n"
        "\tat a.B.c(B.java:1)\n"
        "Caused by: java.io.IOException: disk\n"
        "\tat a.D.e(D.java:2)\n"
    )
    entries = build_entries(text.splitlines())
    assert len(entries) == 1
    assert entries[0].exception_type == "java.io.IOException"


def test_two_untimestamped_errors_stay_separate():
    text = (
        "ERROR first\njava.lang.Exception: one\n\tat a.B.c(B.java:1)\n"
        "ERROR second\njava.lang.Exception: two\n\tat a.B.c(B.java:1)\n"
    )
    assert len(build_entries(text.splitlines())) == 2


def test_hostile_input_is_fast():
    nasty = [
        "java." + "a." * 20000 + "Exception: x",
        "\tat " + "a/" * 20000 + "b(" + "(" * 20000,
        "Caused by: " + "A" * 100000,
        "\tat a.B.c(" + "x" * 100000 + ")",
    ]
    start = time.perf_counter()
    for line in nasty:
        detect_java(line + "\n" + line)
        looks_like_java_exception(line)
    assert time.perf_counter() - start < 1.0
