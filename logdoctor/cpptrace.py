"""Detect C and C++ crashes inside a log record.

C++ has no single trace format, so this reads the ones that show up in logs:

* ``terminate called after throwing an instance of 'T'`` with ``what():``
* ``Assertion `x > 0' failed.``
* signal lines such as ``Caught signal 11 (SIGSEGV)``
* sanitizer reports (AddressSanitizer, ThreadSanitizer, UBSan)

and frames written by glibc ``backtrace_symbols``, gdb or the sanitizers. All of
them list the innermost call first, so frames are reversed (innermost last).
Names are not demangled: ``_ZN3Foo3barEv`` stays as it is.
"""

from __future__ import annotations

import re
from string import hexdigits

from logdoctor.gotrace import strip_call_arguments
from logdoctor.trace import TraceError

_TERMINATE = re.compile(r"terminate called after throwing an instance of '([^']{1,300})'")
_WHAT = re.compile(r"^\s*what\(\):\s?(.{0,2000})$")
_NO_EXCEPTION = re.compile(r"terminate called without an active exception")
_ASSERTION = re.compile(r"(?:^|\s)(\S{1,300}?):(\d{1,9}): (.{0,300}?): Assertion `(.{0,500})' failed")
_SANITIZER = re.compile(r"(?:ERROR|WARNING): ((?:Address|Thread|Memory|Leak|UndefinedBehavior)Sanitizer): (.{0,500})$")
_UBSAN = re.compile(r"(?:^|\s)\S{1,300}?:\d{1,9}(?::\d{1,9})?: runtime error: (.{0,500})$")
_SIGNAL = re.compile(r"\b(SIG(?:SEGV|ABRT|FPE|BUS|ILL|TERM|KILL|PIPE))\b")
_SIGNAL_NAMES = {
    "SIGSEGV": "Segmentation fault",
    "SIGABRT": "Aborted",
    "SIGFPE": "Floating point exception",
    "SIGBUS": "Bus error",
    "SIGILL": "Illegal instruction",
    "SIGTERM": "Terminated",
    "SIGKILL": "Killed",
    "SIGPIPE": "Broken pipe",
}
_SANITIZER_START = re.compile(r"^==\d{1,12}==\s?(?:ERROR|WARNING): \w+Sanitizer")
_SANITIZER_SUMMARY = re.compile(r"^SUMMARY: \w+Sanitizer")
_SANITIZER_ABORT = re.compile(r"^==\d{1,12}==\s?ABORTING")
_SANITIZER_INTERNAL = ("__asan_", "__interceptor_", "__sanitizer_", "__tsan_", "__ubsan_", "__msan_")
_MAX_LINE = 700


# A sanitizer report spans many lines, including unindented ones and blank ones.
# State: 0 = not in a report, 1 = inside it, 2 = after SUMMARY (only ABORTING may still follow).
SAN_NONE, SAN_OPEN, SAN_SUMMARY = 0, 1, 2


def opens_sanitizer_report(line: str) -> bool:
    return bool(_SANITIZER_START.match(line))


def next_sanitizer_state(state: int, line: str) -> int:
    """Move the report state forward after `line` was added to the record."""
    if state == SAN_OPEN and _SANITIZER_SUMMARY.match(line):
        return SAN_SUMMARY
    if state != SAN_NONE and _SANITIZER_ABORT.match(line):
        return SAN_NONE
    return state


def continues_sanitizer_report(state: int, line: str) -> bool:
    return state == SAN_OPEN or (state == SAN_SUMMARY and bool(_SANITIZER_ABORT.match(line)))


def _basename(path: str) -> str:
    return re.split(r"[\\/]", path)[-1] or "?"


def _backtrace_symbols_frame(text: str) -> str | None:
    """'./app(_Z3foov+0x15) [0x401136]' -> 'app:_Z3foov'."""
    if not text.endswith("]"):
        return None
    bracket = text.rfind("[0x")
    if bracket < 1:
        return None
    address = text[bracket + 3 : -1]
    if not address or any(char not in hexdigits for char in address):
        return None
    head = text[:bracket].rstrip()
    if not head.endswith(")"):
        return None
    paren = head.rfind("(")
    if paren < 1:
        return None
    symbol = head[paren + 1 : -1].split("+0x")[0]
    return f"{_basename(head[:paren])}:{symbol or '?'}"


def _numbered_frame(text: str) -> str | None:
    """gdb ('#1  0x... in main () at main.cpp:12') and sanitizer ('#1 0x... in main /a/main.cpp:12:5') frames."""
    if not text.startswith("#"):
        return None
    number, _, rest = text[1:].partition(" ")
    if not number.isdigit() or not rest.strip():
        return None
    rest = rest.strip()
    if rest.startswith("0x"):
        _, _, after = rest.partition(" in ")
        rest = after.strip() if after else rest

    if " at " in rest:
        function, _, location = rest.rpartition(" at ")
    elif " from " in rest:
        function, _, location = rest.rpartition(" from ")
    else:
        function, _, location = rest.rpartition(" ")
        if not function:
            function, location = location, ""
    location = location.strip()
    if location.startswith("(") and location.endswith(")"):
        location = location[1:-1].split("+0x")[0]  # (/lib/libc.so.6+0x29d8f)
    else:
        location = location.split(":")[0]
    function = strip_call_arguments(function.strip()).strip() or "?"
    if function == "??":
        function = "?"
    return f"{_basename(location) if location else '?'}:{function}"


def parse_frame(line: str) -> str | None:
    if not line or len(line) > _MAX_LINE:
        return None
    text = line.strip()
    if text.startswith("#"):
        return _numbered_frame(text)
    return _backtrace_symbols_frame(text)


def is_frame(line: str) -> bool:
    return parse_frame(line) is not None


def _header(lines: list[str]) -> tuple[int, str, str] | None:
    """Find the line that says what went wrong: (index, type, message)."""
    for index, line in enumerate(lines):
        found = _TERMINATE.search(line)
        if found:
            what = ""
            for following in lines[index + 1 : index + 4]:
                match = _WHAT.match(following)
                if match:
                    what = match.group(1).strip()
                    break
            return index, found.group(1), what
        if _NO_EXCEPTION.search(line):
            return index, "terminate", "called without an active exception"
        found = _ASSERTION.search(line)
        if found:
            return index, "assertion", f"{found.group(4)} (in {found.group(3)})"
        found = _SANITIZER.search(line)
        if found:
            message = re.split(r" on (?:unknown )?address| \(|\s{2,}", found.group(2))[0]
            return index, found.group(1), message.strip()
        found = _UBSAN.search(line)
        if found:
            return index, "UndefinedBehaviorSanitizer", found.group(1).strip()
        found = _SIGNAL.search(line)
        if found and re.search(r"signal|received", line, re.IGNORECASE):
            name = found.group(1)
            return index, name, _SIGNAL_NAMES[name]
    return None


def detect_cpp(text: str) -> TraceError | None:
    """Find a C/C++ crash in `text`. Returns None if there is none."""
    lines = text.split("\n")
    header = _header(lines)
    if header is None:
        return None
    start, exception_type, message = header

    frames: list[str] = []
    for line in lines[start + 1 :]:
        frame = parse_frame(line)
        if frame is None:
            if frames:
                break  # the first run of frames is the one that crashed
            continue
        if not frame.split(":", 1)[1].startswith(_SANITIZER_INTERNAL):
            frames.append(frame)
    return TraceError(exception_type, message, list(reversed(frames))[-10:])
