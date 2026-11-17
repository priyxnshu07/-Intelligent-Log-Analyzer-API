import time
from pathlib import Path

from logdoctor import analyze
from logdoctor.cpptrace import detect_cpp, is_frame, parse_frame
from logdoctor.entries import build_entries

FIXTURE = Path(__file__).parent / "fixtures" / "cpp_app.txt"

ASAN = """=================================================================
==4121==ERROR: AddressSanitizer: heap-use-after-free on address 0x602000000010 at pc 0x4a1b2c bp 0x7ffd1 sp 0x7ffd0
READ of size 4 at 0x602000000010 thread T0
    #0 0x4a1b2c in Engine::drain() /srv/engine/engine.cpp:88:12
    #1 0x4a2000 in main /srv/engine/main.cpp:14:5

0x602000000010 is located 0 bytes inside of 4-byte region
freed by thread T0 here:
    #0 0x4a0000 in operator delete(void*) (/srv/engine/engine+0x4a0000)
    #1 0x4a1a00 in Engine::reset() /srv/engine/engine.cpp:70:3

SUMMARY: AddressSanitizer: heap-use-after-free /srv/engine/engine.cpp:88:12 in Engine::drain()
==4121==ABORTING"""


def test_frame_styles():
    assert parse_frame("./engine(_ZN6Engine5drainEv+0x4a) [0x55d1c8a0e12a]") == "engine:_ZN6Engine5drainEv"
    assert parse_frame("/lib/x86_64-linux-gnu/libc.so.6(+0x29d90) [0x7f2a1c829d90]") == "libc.so.6:?"
    assert parse_frame("./app(main+0x15)[0x401136]") == "app:main"
    assert parse_frame("#1  0x000055 in main () at main.cpp:12") == "main.cpp:main"
    assert parse_frame("#2  main (argc=1, argv=0x7ffe) at src/main.cpp:30") == "main.cpp:main"
    assert parse_frame("#0  0x7ff in __pthread_kill () from /lib/x86_64-linux-gnu/libc.so.6") == "libc.so.6:__pthread_kill"
    assert parse_frame("#3  0x0 in ?? ()") == "?:?"
    assert parse_frame("    #0 0x4a1b2c in Engine::drain() /srv/engine/engine.cpp:88:12") == "engine.cpp:Engine::drain"
    assert parse_frame("    #2 0x7f in __libc_start_main (/lib/x86_64-linux-gnu/libc.so.6+0x29d8f)") == "libc.so.6:__libc_start_main"


def test_not_frames():
    for line in (
        "\tat com.acme.Foo.bar(Foo.java:42)",
        "    at getUser (/app/users.js:42:17)",
        '  File "a.py", line 3, in run',
        "main.main()",
        "#hashtag is not a frame",
        "#12",
        "item [0x12] done",
        "(foo) [0xZZ]",
        "",
    ):
        assert not is_frame(line), line


def test_terminate_with_what():
    result = detect_cpp("terminate called after throwing an instance of 'std::bad_alloc'\n  what():  std::bad_alloc\nAborted (core dumped)")
    assert (result.exception_type, result.exception_message) == ("std::bad_alloc", "std::bad_alloc")


def test_terminate_without_exception():
    result = detect_cpp("terminate called without an active exception")
    assert result.exception_type == "terminate"


def test_assertion():
    result = detect_cpp("engine: engine.cpp:120: void Engine::tick(int): Assertion `budget > 0' failed.")
    assert result.exception_type == "assertion"
    assert result.exception_message == "budget > 0 (in void Engine::tick(int))"


def test_signal_lines():
    for line, name in (
        ("Caught signal 11 (SIGSEGV)", "SIGSEGV"),
        ("Program received signal SIGABRT, Aborted.", "SIGABRT"),
        ("*** SIGFPE (@0x7f) received by PID 9 (TID 0x1) from PID 9; stack trace: ***", "SIGFPE"),
    ):
        assert detect_cpp(line).exception_type == name
    assert detect_cpp("Caught signal 11 (SIGSEGV)").exception_message == "Segmentation fault"
    assert detect_cpp("handler mentions SIGSEGV in a comment") is None  # needs 'signal' or 'received'


def test_address_sanitizer_uses_first_stack_only():
    result = detect_cpp(ASAN)
    assert result.exception_type == "AddressSanitizer"
    assert result.exception_message == "heap-use-after-free"
    assert result.frames == ["main.cpp:main", "engine.cpp:Engine::drain"]


def test_sanitizer_runtime_frames_dropped():
    text = (
        "==1==ERROR: AddressSanitizer: stack-buffer-overflow on address 0x1\n"
        "    #0 0x1 in __asan_memcpy (/x/y+0x1)\n"
        "    #1 0x2 in copy_it /a/c.cpp:4:3\n"
    )
    assert detect_cpp(text).frames == ["c.cpp:copy_it"]


def test_other_sanitizers():
    thread = detect_cpp("WARNING: ThreadSanitizer: data race (pid=123)\n  Write of size 4 at 0x1 by thread T1:")
    assert (thread.exception_type, thread.exception_message) == ("ThreadSanitizer", "data race")
    leak = detect_cpp("==9==ERROR: LeakSanitizer: detected memory leaks")
    assert leak.exception_type == "LeakSanitizer"
    ub = detect_cpp("src/math.cpp:12:5: runtime error: signed integer overflow: 2147483647 + 1 cannot be represented in type 'int'")
    assert ub.exception_type == "UndefinedBehaviorSanitizer"
    assert ub.exception_message.startswith("signed integer overflow")


def test_backtrace_after_terminate():
    text = (
        "terminate called after throwing an instance of 'Foo'\n  what():  bad\n"
        "./app(_Z3barv+0x1) [0x401000]\n./app(main+0x5) [0x401010]\n"
    )
    assert detect_cpp(text).frames == ["app:main", "app:_Z3barv"]


def test_go_java_python_node_text_is_not_cpp():
    for text in (
        "panic: runtime error: index out of range [5] with length 3",
        "java.lang.Error: x\n\tat a.B.c(B.java:1)",
        'Traceback (most recent call last):\n  File "a.py", line 1, in f\nKeyError: 1',
        "TypeError: x\n    at a (/x.js:1:1)",
        "an ordinary log line",
    ):
        assert detect_cpp(text) is None


def test_fixture_groups():
    result = analyze(FIXTURE.read_text())
    assert result.summary.languages == ["cpp"]
    terminate = [g for g in result.groups if g.exception_type == "std::runtime_error"]
    assert len(terminate) == 1 and terminate[0].count == 2
    kinds = {g.exception_type for g in result.groups}
    assert {"SIGSEGV", "AddressSanitizer", "assertion"} <= kinds
    asan = next(g for g in result.groups if g.exception_type == "AddressSanitizer")
    assert asan.level == "ERROR" and asan.frames[-1] == "engine.cpp:Engine::drain"
    assert result.summary.level_counts["INFO"] == 2  # the ASan report did not leak into 'restarting'


def test_sanitizer_report_with_blank_lines_is_one_record():
    entries = build_entries(ASAN.splitlines())
    assert len(entries) == 2  # the "=====" banner line, then the report
    assert entries[1].language == "cpp"
    assert entries[1].end_line == len(ASAN.splitlines())  # includes SUMMARY and ABORTING


def test_two_sanitizer_reports_stay_separate():
    entries = build_entries((ASAN + "\n" + ASAN).splitlines())
    assert [e.language for e in entries].count("cpp") == 2


def test_leak_report_ends_at_summary():
    leak = "==7==ERROR: LeakSanitizer: detected memory leaks\n\nDirect leak of 8 byte(s)\n    #0 0x1 in malloc (/x+0x1)\n\nSUMMARY: AddressSanitizer: 8 byte(s) leaked in 1 allocation(s).\n"
    entries = build_entries((leak + "next plain line\nanother line\n").splitlines())
    assert len(entries) == 3  # the report stops at SUMMARY and does not swallow what follows
    assert entries[0].language == "cpp"


def test_unstructured_backtrace_stays_with_error_line():
    text = "ERROR crashed\n./app(main+0x1) [0x401000]\n./app(_start+0x2) [0x401010]\nINFO done\n"
    entries = build_entries(text.splitlines())
    assert entries[0].end_line == 3 and entries[0].language is None  # no header line, so no language


def test_hostile_input_is_fast():
    nasty = [
        "#" + "1" * 50000 + " " + "x" * 50000,
        "#0 0x" + "f" * 50000 + " in " + "(" * 50000,
        "a(" * 30000 + ") [0x" + "1" * 30000 + "]",
        "==1==ERROR: AddressSanitizer: " + "x " * 50000,
        "terminate called after throwing an instance of '" + "a" * 50000,
        "x:1: " + "y" * 50000 + ": Assertion `" + "z" * 50000,
        "SIGSEGV signal " * 10000,
    ]
    text = "\n".join(nasty)
    start = time.perf_counter()
    detect_cpp(text)
    for line in nasty:
        detect_cpp(line + "\n" + line)
        parse_frame(line)
    assert time.perf_counter() - start < 1.0
