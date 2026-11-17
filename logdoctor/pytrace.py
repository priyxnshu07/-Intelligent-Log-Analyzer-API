"""Detect Python tracebacks inside a log record.

Other languages (Java, JavaScript, Go, C++) will get their own detectors
with the same shape: take the text of one record, return what was found.
"""

from __future__ import annotations

import re

from logdoctor.trace import TraceError

TRACEBACK_START = "Traceback (most recent call last):"
CHAIN_MARKERS = (
    "During handling of the above exception",
    "The above exception was the direct cause",
)

_FRAME = re.compile(r'^\s*File "(.{1,500})", line \d+, in (.{1,200})$')
_EXCEPTION = re.compile(r"^([A-Za-z_][\w.]{0,200})(?::\s?(.*))?$")
_PATH_SPLIT = re.compile(r"[\\/]")


PythonError = TraceError


def detect_python(text: str) -> TraceError | None:
    """Find the last traceback in `text`. Returns None if there is none."""
    lines = text.split("\n")

    last = -1
    for index, line in enumerate(lines):
        if line.startswith(TRACEBACK_START):
            last = index
    if last < 0:
        return None

    frames: list[str] = []
    exception_type = None
    exception_message = None
    for line in lines[last + 1 :]:
        frame = _FRAME.match(line)
        if frame:
            filename = _PATH_SPLIT.split(frame.group(1))[-1]
            frames.append(f"{filename}:{frame.group(2).strip()}")
            continue
        if not line.strip() or line[0] in " \t":
            continue  # source line or blank
        found = _EXCEPTION.match(line)
        if found:
            exception_type = found.group(1)
            exception_message = (found.group(2) or "").strip()
            break
    return TraceError(exception_type, exception_message, frames)
