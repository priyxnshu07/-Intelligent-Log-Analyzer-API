"""Detect Java stack traces inside a log record.

Java prints the exception first and then its frames, innermost call first,
followed by "Caused by:" sections. The last cause is the root cause, so that
is what we report. Frames are returned innermost last, like the Python ones.
"""

from __future__ import annotations

import re

from logdoctor.trace import TraceError

# at com.acme.Foo.bar(Foo.java:42)   at java.base/java.lang.Thread.run(Thread.java:829)
_FRAME = re.compile(r"^\s{1,20}at ((?:[\w$.<>-]{1,100}/){0,3}[\w$.<>]{1,300})\(([^()]{0,300})\)\s*$")
_EXCEPTION = re.compile(
    r'^(?:Exception in thread "[^"]{0,200}" )?(Caused by: )?'
    r"([A-Za-z_$][\w$]{0,100}(?:\.[A-Za-z_$][\w$]{0,100}){0,30})(?::\s?(.{0,2000}))?$"
)
_SUPPRESSED = re.compile(r"^\s{1,20}(?:Suppressed|Caused by):")
_ERROR_NAME = ("Exception", "Error", "Throwable")


def looks_like_java_exception(line: str) -> bool:
    """True for a top-level line that names a Java exception, e.g. for attaching to an ERROR line."""
    found = _EXCEPTION.match(line)
    if not found:
        return False
    if found.group(1):
        return True
    name = found.group(2)
    return "." in name and name.endswith(_ERROR_NAME)


def _short(frame_target: str, location: str) -> str:
    """'com.acme.Foo.bar' + 'Foo.java:42' -> 'Foo.java:Foo.bar'."""
    parts = frame_target.split("/")[-1].split(".")
    function = ".".join(parts[-2:]) if len(parts) >= 2 else parts[0]
    filename = location.split(":")[0] if location else ""
    if not filename or filename in ("Native Method", "Unknown Source"):
        filename = parts[-2] if len(parts) >= 2 else "?"
    return f"{filename}:{function}"


def detect_java(text: str) -> TraceError | None:
    """Find the root cause in `text`. Returns None if no Java trace is there."""
    lines = text.split("\n")
    causes: list[tuple[str, str, list[str]]] = []  # type, message, frames (outermost last)
    skipping = False  # inside a "Suppressed:" section, which is not the failure itself

    for index, line in enumerate(lines):
        if _SUPPRESSED.match(line):
            skipping = True
            continue
        frame = _FRAME.match(line)
        if frame:
            if causes and not skipping:
                causes[-1][2].append(_short(frame.group(1), frame.group(2)))
            continue
        found = _EXCEPTION.match(line)
        if not found:
            continue
        name = found.group(2)
        if not (found.group(1) or name.endswith(_ERROR_NAME) or _next_is_frame(lines, index)):
            continue
        causes.append((name, (found.group(3) or "").strip(), []))
        skipping = False

    causes = [cause for cause in causes if cause[2]]  # an exception without frames is not a trace
    if not causes:
        return None
    exception_type, message, frames = causes[-1]
    return TraceError(exception_type, message, list(reversed(frames))[-10:])


def _next_is_frame(lines: list[str], index: int) -> bool:
    return index + 1 < len(lines) and bool(_FRAME.match(lines[index + 1]))
