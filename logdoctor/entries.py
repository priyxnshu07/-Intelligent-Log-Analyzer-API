"""Turn raw lines into log records.

A record is one log line plus any lines that belong to it, such as a stack
trace. Logs with timestamps or levels are split on those; plain text is
split into one record per non-indented line.
"""

from __future__ import annotations

import re

from logdoctor.cpptrace import (
    SAN_NONE,
    SAN_OPEN,
    continues_sanitizer_report,
    detect_cpp,
    is_frame,
    next_sanitizer_state,
    opens_sanitizer_report,
)
from logdoctor.gotrace import detect_go, is_goroutine_header
from logdoctor.header import MAX_MESSAGE_CHARS, Header, parse_header
from logdoctor.javatrace import detect_java, looks_like_java_exception
from logdoctor.levels import WARNING_RANK, rank
from logdoctor.models import LogEntry
from logdoctor.nodetrace import detect_node, looks_like_js_exception
from logdoctor.pytrace import CHAIN_MARKERS, TRACEBACK_START, detect_python

MAX_TEXT_CHARS = 4000
STRUCTURED_RATIO = 0.25  # share of top-level lines that must look like log records

# Words that suggest a failure when a line has no explicit level.
_FAILURE_WORDS = re.compile(
    r"\b\w*(?:error|exception)\b|\b(?:traceback|fatal|panic|segmentation fault|"
    r"failed|failure|unhandled|out of memory|terminate called|aborted|assertion|"
    r"\w+sanitizer|sig(?:segv|abrt|fpe|bus|ill))\b",
    re.IGNORECASE,
)
_EXCEPTION_NAME = re.compile(r"\b([A-Za-z_][\w.]*(?:Error|Exception))\b")


class _Draft:
    """A record being assembled."""

    __slots__ = ("start", "end", "header", "level", "inferred", "lines", "traceback_open", "go_trace", "go_open", "san_state")

    def __init__(self, index: int, line: str, header: Header | None, *, is_traceback: bool):
        self.start = index
        self.end = index
        self.header = header
        self.lines = [line]
        self.traceback_open = is_traceback
        self.go_trace = False  # this record holds a Go goroutine dump
        self.go_open = False  # inside a goroutine dump, which a blank line ends
        self.san_state = SAN_OPEN if opens_sanitizer_report(line) else SAN_NONE  # sanitizer report progress
        if is_traceback:
            self.level, self.inferred = "ERROR", True
        elif header is None:
            self.level, self.inferred = "UNKNOWN", False
        elif header.level != "UNKNOWN":
            self.level, self.inferred = header.level, False
        elif _FAILURE_WORDS.search(header.message):
            self.level, self.inferred = "ERROR", True
        else:
            self.level, self.inferred = "UNKNOWN", False

    def add(self, index: int, line: str) -> None:
        self.end = index
        self.lines.append(line)


def build_entries(lines: list[str], first_line_no: int = 1) -> list[LogEntry]:
    """Group `lines` into records. `first_line_no` is the number of lines[0]."""
    headers = [parse_header(line) for line in lines]
    top_level = sum(1 for line in lines if line.strip() and line[0] not in " \t")
    strong = sum(1 for header in headers if header and header.strong)
    structured = strong > 0 and strong >= STRUCTURED_RATIO * top_level

    drafts: list[_Draft] = []
    current: _Draft | None = None

    for index, line in enumerate(lines):
        if not line.strip():
            if current:
                current.go_open = False
            continue
        header = headers[index]
        is_traceback = line.startswith(TRACEBACK_START)
        is_chain = line.startswith(CHAIN_MARKERS)

        if is_chain:
            starts = current is None
        elif is_traceback:
            # logging.exception() style: the trace belongs to the error line before it.
            starts = current is None or rank(current.level) < WARNING_RANK
        elif opens_sanitizer_report(line):
            starts = True  # a sanitizer report is its own error, whatever came before it
        elif structured:
            starts = bool(header and header.strong)
        else:
            top = line[0] not in " \t"
            starts = top and not (current and current.traceback_open)
            if starts and current and _continues_trace(line, lines[index + 1 :][:1], current):
                starts = False

        if starts or current is None:
            current = _Draft(index, line, header, is_traceback=is_traceback)
            drafts.append(current)
            if is_goroutine_header(line):
                current.go_trace = current.go_open = True
            continue

        current.add(index, line)
        if opens_sanitizer_report(line):
            current.san_state = SAN_OPEN
        else:
            current.san_state = next_sanitizer_state(current.san_state, line)
        if is_goroutine_header(line):
            current.go_trace = current.go_open = True
        elif line.startswith("exit status "):
            current.go_open = False  # last line of a crashed Go program's output
        if is_traceback or is_chain:
            current.traceback_open = is_traceback
        elif current.traceback_open and line[0] not in " \t":
            current.traceback_open = False  # that was the exception line

    return [_finish(draft, first_line_no) for draft in drafts]


def _continues_trace(line: str, upcoming: list[str], current: _Draft) -> bool:
    """An exception line right after an error line belongs to that error."""
    if current.go_open or continues_sanitizer_report(current.san_state, line):
        return True  # function lines of a Go dump and lines of a sanitizer report are not indented
    if rank(current.level) >= WARNING_RANK and is_frame(line):
        return True  # a C++ backtrace line after an error line
    if is_goroutine_header(line):
        return current.go_trace or rank(current.level) >= WARNING_RANK
    if line.startswith("[signal ") and rank(current.level) >= WARNING_RANK:
        return True
    if line.startswith("Caused by:"):
        return True
    if rank(current.level) < WARNING_RANK:
        return False
    next_line = upcoming[0] if upcoming else None
    return looks_like_java_exception(line) or looks_like_js_exception(line, next_line)


def _finish(draft: _Draft, first_line_no: int) -> LogEntry:
    full_text = "\n".join(draft.lines)
    header = draft.header
    message = header.message if header else draft.lines[0].strip()[:MAX_MESSAGE_CHARS]

    entry = LogEntry(
        line=first_line_no + draft.start,
        end_line=first_line_no + draft.end,
        timestamp=header.timestamp if header else None,
        level=draft.level,
        level_inferred=draft.inferred,
        message=message,
        text=_shorten(full_text),
    )

    language, trace = "python", detect_python(full_text)
    if trace is None:
        language, trace = "java", detect_java(full_text)
    if trace is None:
        language, trace = "javascript", detect_node(full_text)
    if trace is None:
        language, trace = "go", detect_go(full_text)
    if trace is None:
        language, trace = "cpp", detect_cpp(full_text)
    if trace:
        entry.language = language
        entry.exception_type = trace.exception_type
        entry.exception_message = trace.exception_message
        entry.frames = trace.frames[-10:]
        if entry.level == "UNKNOWN":
            entry.level, entry.level_inferred = "ERROR", True
    else:
        named = _EXCEPTION_NAME.search(message)
        if named:
            entry.exception_type = named.group(1)
    return entry


def _shorten(text: str) -> str:
    """Keep the start and the end of a long record. The end holds the final error."""
    if len(text) <= MAX_TEXT_CHARS:
        return text
    return text[:1500] + "\n... [truncated] ...\n" + text[-2500:]
