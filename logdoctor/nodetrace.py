"""Detect JavaScript (Node.js and Chrome-style) stack traces inside a log record.

    TypeError: Cannot read properties of undefined (reading 'id')
        at getUser (/app/src/users.js:42:17)
        at /app/src/server.js:10:5

Frames list the innermost call first, so they are reversed to put the
innermost last like the other languages. Newer Node prints a cause as an
indented "[cause]: ..." line; the last cause is reported as the root cause.
Frames are read with plain string handling, not one big regex, so odd lines
cannot make the matching slow.
"""

from __future__ import annotations

import re

from logdoctor.trace import TraceError

MAX_FRAME_CHARS = 600
_EXCEPTION = re.compile(
    r"^(?:Uncaught |\(node:\d{1,10}\) (?:\w{1,60}: )?)?"
    r"([A-Za-z_$][\w$]{0,100})(?: \[[\w$.-]{1,60}\])?(?:: (.{0,2000}))?$"
)
_CAUSE = re.compile(r"^\s{1,20}\[cause\]: (.{1,2500})$")
_ERROR_NAME = ("Error", "Exception")


def parse_frame(line: str) -> str | None:
    """'    at fn (/a/b.js:1:2)' -> 'b.js:fn'. None if the line is not a JS frame."""
    if not line or line[0] not in " \t" or len(line) > MAX_FRAME_CHARS:
        return None
    body = line.strip()
    if not body.startswith("at "):
        return None
    body = body[3:]
    if body.endswith(")"):
        split = body.find(" (")
        if split < 0:
            return None
        name, location = body[:split], body[split + 2 : -1]
    else:
        name, location = "", body

    pieces = location.rsplit(":", 2)
    if len(pieces) == 3 and pieces[1].isdigit() and pieces[2].isdigit():
        path = pieces[0]
    elif location in ("native", "<anonymous>") or location.startswith("index "):
        path = "<native>"
    else:
        return None

    filename = re.split(r"[\\/]", path)[-1].split("?")[0] or "?"
    if " " in filename:
        filename = "<eval>"
    for prefix in ("async ", "new "):
        if name.startswith(prefix):
            name = name[len(prefix):]
    name = name.split(" [as ")[0].strip() or "<anonymous>"
    return f"{filename}:{name}"


def looks_like_js_exception(line: str, next_line: str | None) -> bool:
    """True for a top-level exception line that is followed by a JS frame."""
    if not next_line or parse_frame(next_line) is None:
        return False
    return bool(line and line[0] not in " \t" and _EXCEPTION.match(line))


def detect_node(text: str) -> TraceError | None:
    """Find the root cause in `text`. Returns None if no JS trace is there."""
    lines = text.split("\n")
    causes: list[tuple[str, str, list[str]]] = []  # type, message, frames (outermost last)

    for index, line in enumerate(lines):
        frame = parse_frame(line)
        if frame:
            if causes:
                causes[-1][2].append(frame)
            continue
        cause = _CAUSE.match(line)
        candidate = cause.group(1) if cause else line
        found = _EXCEPTION.match(candidate)
        if not found:
            continue
        name = found.group(1)
        next_line = lines[index + 1] if index + 1 < len(lines) else None
        if not (cause or name.endswith(_ERROR_NAME) or parse_frame(next_line or "")):
            continue
        causes.append((name, (found.group(2) or "").strip(), []))

    causes = [cause for cause in causes if cause[2]]
    if not causes:
        return None
    exception_type, message, frames = causes[-1]
    return TraceError(exception_type, message, list(reversed(frames))[-10:])
