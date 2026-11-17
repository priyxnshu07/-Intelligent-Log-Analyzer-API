import time
from pathlib import Path

from logdoctor import analyze
from logdoctor.entries import build_entries
from logdoctor.gotrace import detect_go, is_goroutine_header
from logdoctor.header import parse_header

FIXTURE = Path(__file__).parent / "fixtures" / "go_app.txt"

PANIC = """panic: runtime error: index out of range [5] with length 3

goroutine 1 [running]:
main.pick(...)
\t/app/main.go:10
main.main()
\t/app/main.go:5 +0x1d
exit status 2"""


def test_simple_panic():
    result = detect_go(PANIC)
    assert result.exception_type == "panic"
    assert result.exception_message == "runtime error: index out of range [5] with length 3"
    assert result.frames == ["main.go:main.main", "main.go:main.pick"]  # innermost last


def test_runtime_frames_are_dropped():
    text = (
        "panic: boom\n\ngoroutine 1 [running]:\n"
        "panic({0x6a1b20, 0xc0001a2000})\n\t/usr/local/go/src/runtime/panic.go:884 +0x213\n"
        "runtime.gopanic(...)\n\t/usr/local/go/src/runtime/panic.go:100\n"
        "main.work()\n\t/app/w.go:3 +0x1\n"
    )
    assert detect_go(text).frames == ["w.go:main.work"]


def test_methods_closures_and_arguments():
    text = (
        "panic: x\n\ngoroutine 7 [running]:\n"
        "main.(*Server).handle(0xc0000a4000, {0x7c2f10, 0xc0001b6000}, 0xc0001b8000)\n\t/a/s.go:48 +0x1a5\n"
        "main.run.func1()\n\t/a/r.go:9 +0x2\n"
        "created by main.run in goroutine 1\n\t/a/r.go:12 +0x5\n"
    )
    # "created by" belongs to the goroutine, not to the call stack
    assert detect_go(text).frames == ["r.go:main.run.func1", "s.go:main.(*Server).handle"]


def test_fatal_error():
    result = detect_go("fatal error: all goroutines are asleep - deadlock!\n\ngoroutine 1 [chan receive]:\nmain.main()\n\t/a/b.go:5 +0x1\n")
    assert result.exception_type == "fatal error"
    assert result.exception_message == "all goroutines are asleep - deadlock!"


def test_http_recovered_panic():
    text = (
        "2024/05/01 10:00:00 http: panic serving 10.0.0.9:51234: runtime error: nil map\n"
        "goroutine 33 [running]:\n"
        "net/http.(*conn).serve.func1()\n\t/usr/local/go/src/net/http/server.go:1850 +0xbf\n"
        "main.h()\n\t/a/h.go:4 +0x1\n"
    )
    result = detect_go(text)
    assert result.exception_type == "panic"
    assert result.exception_message == "runtime error: nil map"
    assert result.frames == ["h.go:main.h"]


def test_only_first_goroutine_is_used():
    text = (
        "panic: x\n\ngoroutine 1 [running]:\nmain.a()\n\t/a/a.go:1 +0x1\n\n"
        "goroutine 2 [select]:\nmain.b()\n\t/a/b.go:2 +0x1\n"
    )
    assert detect_go(text).frames == ["a.go:main.a"]


def test_panic_without_trace_still_counts():
    result = detect_go("panic: something broke")
    assert result.exception_type == "panic" and result.frames == []


def test_no_panic_means_none():
    assert detect_go("everything fine") is None
    assert detect_go("goroutine 1 [running]:\nmain.main()\n\t/a/b.go:1") is None
    assert detect_go("do not panic: it is fine") is not None  # known: a bare 'panic: ' phrase counts
    assert detect_go("the panic was handled") is None


def test_goroutine_header():
    assert is_goroutine_header("goroutine 1 [running]:")
    assert is_goroutine_header("goroutine 18 [chan receive, 5 minutes]:")
    assert not is_goroutine_header("goroutine started")
    assert not is_goroutine_header("  goroutine 1 [running]:")


def test_go_log_dates_with_slashes():
    header = parse_header("2024/05/01 10:00:00 something failed")
    assert header.timestamp.year == 2024 and header.timestamp.month == 5
    assert header.message == "something failed"


def test_fixture_groups():
    result = analyze(FIXTURE.read_text())
    assert result.summary.languages == ["go"]
    db = [g for g in result.groups if "connection to" in g.title]
    assert len(db) == 1 and db[0].count == 2  # 30s and 31s are the same problem
    panics = [g for g in result.groups if g.exception_type == "panic"]
    assert len(panics) == 2
    assert {g.frames[-1] for g in panics} == {"handlers.go:main.pick", "main.go:main.process"}


def test_untimestamped_dump_is_one_record():
    entries = build_entries(PANIC.splitlines())
    assert len(entries) == 1
    assert entries[0].language == "go"
    assert entries[0].end_line == len(PANIC.splitlines())


def test_signal_line_and_blank_line_stay_in_the_panic():
    text = "panic: boom\n[signal SIGSEGV: segmentation violation code=0x1]\n\ngoroutine 1 [running]:\nmain.f()\n\t/a/b.go:1 +0x1\n"
    entries = build_entries(text.splitlines())
    assert len(entries) == 1 and entries[0].exception_message == "boom"


def test_output_after_exit_status_starts_a_new_record():
    text = PANIC + "\nstarting again\nwork continues\n"
    entries = build_entries(text.splitlines())
    assert len(entries) == 3
    assert entries[1].message == "starting again"


def test_two_crashes_stay_separate():
    entries = build_entries((PANIC + "\n" + PANIC).splitlines())
    assert len(entries) == 2


def test_hostile_input_is_fast():
    nasty = [
        "panic: " + "x" * 100000,
        "goroutine " + "1" * 50000 + " [running]:",
        "\t" + "/a" * 50000 + ".go:" + "9" * 50000,
        "main." + "(" * 50000,
        "main.f" + "(" * 30000 + ")" * 30000,
        "http: panic serving " + "a" * 100000 + ": x",
    ]
    text = "panic: x\n\ngoroutine 1 [running]:\n" + "\n".join(nasty)
    start = time.perf_counter()
    detect_go(text)
    for line in nasty:
        detect_go(line + "\n" + line)
    assert time.perf_counter() - start < 1.0
