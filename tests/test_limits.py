"""The engine runs on a public server, so hostile or huge input must stay fast."""

import time

import pytest

from logdoctor import analyze

SECONDS = 5  # generous: shared CI machines are slow


def timed(text, **kwargs):
    start = time.perf_counter()
    result = analyze(text, **kwargs)
    return result, time.perf_counter() - start


def test_fifty_thousand_lines_is_fast():
    lines = []
    for i in range(50_000):
        level = "ERROR" if i % 7 == 0 else "INFO"
        lines.append(f"2026-11-18 01:{(i // 60) % 60:02d}:{i % 60:02d} {level} svc request {i} took {i % 90}ms")
    result, elapsed = timed("\n".join(lines))
    assert result.summary.entries == 50_000
    assert result.summary.truncated is False
    assert elapsed < SECONDS


def test_one_megabyte_single_line_is_fast():
    result, elapsed = timed("x" * 1_000_000)
    assert result.summary.entries == 1
    assert elapsed < SECONDS


@pytest.mark.parametrize(
    "line",
    [
        "[" * 5000,
        "ERROR " * 3000,
        "0" * 10_000,
        "a" * 9_999 + "Error",
        "1.2.3.4" * 1500,
        "/" + "a/" * 4000,
        "2026-11-18 01:00:00 " * 500,
        "File \"" * 1500,
        "[ERROR]" * 1500,
        "0x" + "f" * 9000,
        "\\" * 8000,
    ],
)
def test_pathological_lines_do_not_blow_up(line):
    _, elapsed = timed(line + "\n" + line)
    assert elapsed < SECONDS


def test_pathological_traceback_is_fast():
    frames = '  File "a/b/c.py", line 1, in f\n' * 20_000
    text = "2026-11-18 01:00:00 ERROR x\nTraceback (most recent call last):\n" + frames + "ValueError: v"
    result, elapsed = timed(text)
    assert result.groups[0].exception_type == "ValueError"
    assert elapsed < SECONDS


def test_binary_looking_input_does_not_crash():
    text = "".join(chr(i % 1114111 if i % 1114111 not in range(0xD800, 0xE000) else 65) for i in range(0, 200_000, 7))
    result = analyze(text)
    assert result.summary.entries >= 1


def test_every_line_is_cut_to_a_maximum_length():
    result = analyze("2026-11-18 01:00:00 ERROR " + "z" * 100_000)
    assert len(result.groups[0].sample) < 4100
