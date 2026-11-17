"""Detect Go panics and fatal errors inside a log record.

    panic: runtime error: index out of range [5] with length 3

    goroutine 1 [running]:
    main.pick(...)
    	/app/main.go:10
    main.main()
    	/app/main.go:5 +0x1d

Each frame is two lines: the function (not indented), then its file and line
(indented). The first goroutine is the one that crashed. Frames come
innermost first, so they are reversed to put the innermost last.
"""

from __future__ import annotations

import re

from logdoctor.trace import TraceError

GOROUTINE = re.compile(r"^goroutine \d{1,12} \[[^\]]{1,80}\]:")
_PANIC = re.compile(r"(?:^|[\s\]:])(panic|fatal error): (.{0,2000})$")
# net/http recovers handler panics and logs: http: panic serving 10.0.0.9:51234: <message>
_HTTP_PANIC = re.compile(r"(?:^|[\s\]:])http: panic serving \S{1,100}: (.{0,2000})$")
_FRAMEWORK_FUNCTIONS = ("runtime.", "runtime/", "net/http.(*conn).serve")
_SKIP_FUNCTION_PREFIXES = ("created by ", "goroutine ", "exit status", "[signal", "panic(")


def is_goroutine_header(line: str) -> bool:
    return bool(GOROUTINE.match(line))


def _function_name(line: str) -> str:
    """'main.(*Server).Handle(0xc0001, {0x4, 0x5})' -> 'main.(*Server).Handle'."""
    text = line.strip()
    if not text.endswith(")"):
        return text
    depth = 0
    for index in range(len(text) - 1, -1, -1):
        if text[index] == ")":
            depth += 1
        elif text[index] == "(":
            depth -= 1
            if depth == 0:
                return text[:index] or text
    return text


def _location(line: str) -> str | None:
    """'\\t/app/main.go:42 +0x1d' -> 'main.go'."""
    if not line or line[0] not in " \t" or len(line) > 700:
        return None
    text = line.strip().rsplit(" +0x", 1)[0]
    path, _, number = text.rpartition(":")
    if not number.isdigit() or not path.endswith(".go"):
        return None
    return re.split(r"[\\/]", path)[-1]


def detect_go(text: str) -> TraceError | None:
    """Find a panic or fatal error in `text`. Returns None if there is none."""
    lines = text.split("\n")
    kind = message = None
    start = 0
    for index, line in enumerate(lines):
        match = _HTTP_PANIC.search(line)
        if match:
            kind, message = "panic", match.group(1)
        else:
            match = _PANIC.search(line)
            if match:
                kind, message = match.group(1), match.group(2)
        if kind:
            start = index
            break
    if not kind:
        return None

    frames: list[str] = []
    in_trace = False
    pending: str | None = None
    for line in lines[start + 1 :]:
        if is_goroutine_header(line):
            if in_trace:
                break  # only the first goroutine, the one that crashed
            in_trace = True
            continue
        if not in_trace:
            continue
        if not line.strip():
            break
        file = _location(line)
        if file and pending:
            if not pending.startswith(_FRAMEWORK_FUNCTIONS):
                frames.append(f"{file}:{pending}")
            pending = None
        elif line[0] not in " \t" and not line.startswith(_SKIP_FUNCTION_PREFIXES):
            pending = _function_name(line)

    return TraceError(kind, message.strip(), list(reversed(frames))[-10:])
