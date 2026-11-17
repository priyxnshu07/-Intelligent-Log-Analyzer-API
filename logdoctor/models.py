"""Data structures returned by the engine."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime


@dataclass
class LogEntry:
    """One log record. A stack trace stays attached to the line that caused it."""

    line: int  # first line number in the original input (1-based)
    end_line: int
    timestamp: datetime | None  # naive, converted to UTC when the log had a zone
    level: str  # DEBUG, INFO, WARNING, ERROR, CRITICAL or UNKNOWN
    level_inferred: bool  # True when we guessed the level instead of reading it
    message: str  # first line without timestamp and level
    text: str  # whole record (long ones are shortened)
    language: str | None = None  # set when a language-specific trace was found
    exception_type: str | None = None
    exception_message: str | None = None
    frames: list[str] = field(default_factory=list)  # "file:function", innermost last


@dataclass
class ProbableCause:
    """A rule-based hint about why a problem happens. A suggestion, not proof."""

    id: str  # rule id, stable
    cause: str  # short statement
    explanation: str  # why this usually happens
    steps: list[str]  # what to check, in order
    matched: str  # the text from the log that triggered the rule
    where: str  # "message" (exception type or title) or "stack trace" (weaker evidence)


@dataclass
class ErrorGroup:
    """Repeated occurrences of the same problem."""

    id: str
    level: str  # most severe level seen in the group
    title: str  # message of the first occurrence
    pattern: str  # message with ids, numbers and paths masked
    exception_type: str | None
    language: str | None
    count: int
    first_seen: datetime | None
    last_seen: datetime | None
    first_line: int
    last_line: int
    lines: list[int]  # first few line numbers, used as evidence
    frames: list[str]
    sample: str  # full text of the first occurrence
    causes: list[ProbableCause] = field(default_factory=list)  # best matches first, may be empty


@dataclass
class TimelineBucket:
    start: datetime
    errors: int  # ERROR and CRITICAL entries
    warnings: int


@dataclass
class Timeline:
    bucket_seconds: int | None
    has_timestamps: bool
    buckets: list[TimelineBucket]


@dataclass
class Summary:
    total_lines: int
    lines_analyzed: int
    truncated: bool  # True when only the most recent lines were analyzed
    entries: int
    level_counts: dict[str, int]
    error_count: int  # ERROR and CRITICAL entries
    warning_count: int
    group_count: int
    first_timestamp: datetime | None
    last_timestamp: datetime | None
    languages: list[str]


@dataclass
class Analysis:
    summary: Summary
    groups: list[ErrorGroup]
    timeline: Timeline

    def to_dict(self) -> dict:
        """Plain dict that is safe to turn into JSON."""
        return json.loads(json.dumps(asdict(self), default=_json_default))

    def to_json(self, indent: int | None = None) -> str:
        return json.dumps(asdict(self), default=_json_default, indent=indent)


def _json_default(value):
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError(f"cannot serialize {type(value).__name__}")
