"""Logs with fields: JSON lines and CSV with a header row.

Each line becomes a record with a timestamp, level and message read from the
usual field names (msg, message, level, severity, time, ts, @timestamp ...).
Other fields (request ids, durations) are ignored for grouping, which is what
makes repeated errors group even though those fields differ.

Every line is read on its own. A CSV value that contains a line break is not
supported, and neither is pretty-printed (multi-line) JSON.
"""

from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from logdoctor.header import find_timestamp
from logdoctor.levels import normalize_level

MAX_MESSAGE_CHARS = 500
_TIME_KEYS = ("@timestamp", "timestamp", "time", "ts", "datetime", "asctime", "date", "t")
_LEVEL_KEYS = ("level", "log.level", "severity", "levelname", "lvl", "loglevel", "log_level", "@l")
_MESSAGE_KEYS = ("message", "msg", "@message", "@m", "event", "text", "log", "description", "summary")
_ERROR_TYPE_KEYS = ("error.type", "err.type", "exception.type", "error.name", "err.name",
                    "error.class", "exception.class", "exc_type", "exception_type")
_ERROR_MESSAGE_KEYS = ("error.message", "err.message", "exception.message", "exc_message", "exception_message")
_STACK_KEYS = ("error.stack_trace", "error.stack", "err.stack", "exception.stacktrace", "exception.stack",
               "stack_trace", "stacktrace", "stack", "traceback", "exc_info", "exception", "error", "err")
# pino and bunyan write levels as numbers
_NUMERIC_LEVELS = ((10, "DEBUG"), (20, "DEBUG"), (30, "INFO"), (40, "WARNING"), (50, "ERROR"))
_CSV_COLUMN = re.compile(r"^[A-Za-z_@][\w.@ -]{0,40}$")
_CSV_DELIMITERS = ",;\t|"


@dataclass
class StructuredRecord:
    timestamp: datetime | None
    level: str  # normalized, or "UNKNOWN"
    level_inferred: bool  # True when no level field existed but an error was attached
    message: str
    trace_text: str | None  # stack trace text found in a field, for the language detectors
    exception_type: str | None
    exception_message: str | None


def _flatten(mapping: dict) -> dict[str, Any]:
    """Lower-case keys, with nested objects reachable as 'parent.child'."""
    flat: dict[str, Any] = {}
    for key, value in mapping.items():
        if not isinstance(key, str):
            continue
        name = key.lower()
        flat.setdefault(name, value)
        if isinstance(value, dict):
            for inner_key, inner in value.items():
                if isinstance(inner_key, str):
                    flat.setdefault(f"{name}.{inner_key.lower()}", inner)
    return flat


def _first_text(flat: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = flat.get(key)
        if isinstance(value, str) and value.strip():
            return value
        if isinstance(value, (int, float)) and not isinstance(value, bool) and key in _MESSAGE_KEYS:
            return str(value)
    return None


def _timestamp(flat: dict[str, Any]) -> datetime | None:
    for key in _TIME_KEYS:
        value = flat.get(key)
        if isinstance(value, bool) or value is None:
            continue
        if isinstance(value, str):
            found = find_timestamp(value)
            if found:
                return found
            value = _number(value)
        if isinstance(value, (int, float)):
            found = _epoch(value)
            if found:
                return found
    return None


def _number(text: str) -> float | None:
    try:
        return float(text.strip())
    except ValueError:
        return None


def _epoch(value: float) -> datetime | None:
    """Seconds or milliseconds since 1970, as long as it falls in a sensible range."""
    if 1e9 <= value < 4e9:
        seconds = value
    elif 1e12 <= value < 4e12:
        seconds = value / 1000
    else:
        return None
    try:
        return datetime.fromtimestamp(seconds, timezone.utc).replace(tzinfo=None)
    except (OverflowError, OSError, ValueError):
        return None


def _level(flat: dict[str, Any]) -> str:
    for key in _LEVEL_KEYS:
        value = flat.get(key)
        if isinstance(value, bool) or value is None:
            continue
        if isinstance(value, str):
            level = normalize_level(value.strip())
            if level != "UNKNOWN":
                return level
            value = _number(value)
        if isinstance(value, (int, float)):
            if value >= 60:
                return "CRITICAL"
            for limit, name in _NUMERIC_LEVELS:
                if value <= limit:
                    return name
    return "UNKNOWN"


def record_from_mapping(mapping: dict, fallback_text: str = "") -> StructuredRecord | None:
    """Build a record from parsed fields. None if this does not look like a log record."""
    flat = _flatten(mapping)
    timestamp = _timestamp(flat)
    level = _level(flat)
    message = _first_text(flat, _MESSAGE_KEYS)

    error_type = _first_text(flat, _ERROR_TYPE_KEYS)
    error_message = _first_text(flat, _ERROR_MESSAGE_KEYS)
    stack = _first_text(flat, _STACK_KEYS)
    trace_text = None
    if stack:
        if "\n" in stack:
            trace_text = stack
        elif not error_message:
            error_message = stack  # "error": "connection refused"

    if message is None and not (error_message or trace_text) and level == "UNKNOWN" and timestamp is None:
        return None  # JSON or CSV data that is not a log line
    if message is None:
        message = error_message or (trace_text or "").split("\n", 1)[0] or fallback_text.strip() or "(no message)"

    inferred = False
    if level == "UNKNOWN" and (error_type or error_message or trace_text):
        level, inferred = "ERROR", True
    return StructuredRecord(
        timestamp=timestamp,
        level=level,
        level_inferred=inferred,
        message=" ".join(message.split())[:MAX_MESSAGE_CHARS],
        trace_text=trace_text,
        exception_type=error_type,
        exception_message=error_message,
    )


def parse_json_line(line: str) -> StructuredRecord | None:
    """Read one JSON-lines record. None if the line is not a JSON object with log fields."""
    if not line.startswith("{"):
        return None
    text = line.rstrip()
    if not text.endswith("}"):
        return None
    try:
        data = json.loads(text)
    except (ValueError, RecursionError):
        return None
    return record_from_mapping(data, text) if isinstance(data, dict) else None


@dataclass(frozen=True)
class CsvLayout:
    delimiter: str
    columns: tuple[str, ...]


def detect_csv(lines: list[str]) -> tuple[int, CsvLayout] | None:
    """Find a CSV header row near the top: (index of the header line, layout)."""
    for index, line in enumerate(lines[:5]):
        if not line.strip():
            continue
        delimiter = max(_CSV_DELIMITERS, key=line.count)
        if line.count(delimiter) < 1:
            return None
        try:
            columns = next(csv.reader([line], delimiter=delimiter))
        except (csv.Error, StopIteration):
            return None
        names = [column.strip().lower() for column in columns]
        if not all(_CSV_COLUMN.match(name) for name in names):
            return None
        has_message = any(name in _MESSAGE_KEYS for name in names)
        has_context = any(name in _LEVEL_KEYS or name in _TIME_KEYS for name in names)
        if has_message and has_context:
            return index, CsvLayout(delimiter, tuple(names))
        return None
    return None


def parse_csv_line(layout: CsvLayout, line: str) -> StructuredRecord | None:
    if not line.strip():
        return None
    try:
        row = next(csv.reader([line], delimiter=layout.delimiter))
    except (csv.Error, StopIteration):
        return None
    if len(row) < 2:
        return None
    mapping = {name: value for name, value in zip(layout.columns, row) if value.strip()}
    return record_from_mapping(mapping, line)
