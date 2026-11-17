"""Read the timestamp and level from the start of a log line.

Every pattern here is anchored or looks at a short prefix of the line, so
a hostile or huge line cannot make the regexes run for a long time.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta

from logdoctor.levels import normalize_level

PREFIX_CHARS = 200  # only the start of a line is inspected
TS_NEAR_CHARS = 40  # a timestamp this close to the start marks a new record
LEVEL_NEAR_CHARS = 60
MAX_MESSAGE_CHARS = 500

_TS = re.compile(
    r"(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2}):(\d{2})"
    r"(?:[.,](\d{1,9}))?(?:\s?(Z|[+-]\d{2}:?\d{2}))?"
)

_WORDS = (
    "TRACE|DEBUG|DEBU|INFO|NOTICE|WARNING|WARN|ERROR|ERRO|ERR|"
    "CRITICAL|FATAL|FATA|SEVERE|PANIC|PANI"
)
# [ERROR]
_BRACKET = re.compile(rf"\[({_WORDS})\]", re.IGNORECASE)
# 2026-01-01 12:00:00 ERROR something   /   ERROR[0000] something (logrus)
_UPPER = re.compile(rf"(?:^|[\s|\-:])({_WORDS})(?=[\s:\]|\[\-]|$)")
# "error: something" / "Error: something" at the very start of the line
_LEAD = re.compile(rf"^({_WORDS})\s*:\s", re.IGNORECASE)
# level=error  /  "level":"error"
_KV = re.compile(rf'\blevel"?\s*[=:]\s*"?({_WORDS})\b', re.IGNORECASE)

# winston/pino-style "2024-05-01T10:00:00Z info: message": the level follows the
# timestamp in any case, and needs the colon so plain words are not mistaken for it.
_AFTER_TS = re.compile(rf"\s{{0,3}}({_WORDS})\s{{0,2}}:", re.IGNORECASE)

_EMPTY_BRACKETS = re.compile(r"\[\s*\]")


@dataclass(frozen=True)
class Header:
    timestamp: datetime | None
    level: str  # normalized, or "UNKNOWN"
    message: str
    strong: bool  # True when the line looks like the first line of a log record


def parse_timestamp(match: re.Match) -> datetime | None:
    """Turn a timestamp match into a naive UTC datetime, or None if invalid."""
    try:
        year, month, day, hour, minute, second = (int(match.group(i)) for i in range(1, 7))
        fraction = match.group(7)
        micro = int(fraction.ljust(6, "0")[:6]) if fraction else 0
        moment = datetime(year, month, day, hour, minute, second, micro)
        zone = match.group(8)
        if zone and zone != "Z":
            sign = -1 if zone[0] == "-" else 1
            digits = zone[1:].replace(":", "")
            offset = timedelta(hours=int(digits[:2]), minutes=int(digits[2:4]))
            moment = moment - sign * offset
        return moment
    except (ValueError, OverflowError):
        return None


def parse_header(line: str) -> Header | None:
    """Return the header of a log line, or None for indented continuation lines."""
    if not line or line[0] in " \t":
        return None

    head = line[:PREFIX_CHARS]

    timestamp = None
    ts_span = None
    ts_match = _TS.search(head)
    if ts_match:
        timestamp = parse_timestamp(ts_match)
        if timestamp is not None:
            ts_span = ts_match.span()
    ts_near = ts_span is not None and ts_span[0] <= TS_NEAR_CHARS

    level_word = None
    level_span = None
    level_strong = False

    match = _BRACKET.search(head[:80])
    if match and match.start() <= LEVEL_NEAR_CHARS:
        level_word, level_span, level_strong = match.group(1), match.span(), True
    else:
        match = _UPPER.search(head[:80])
        if match and match.start(1) <= LEVEL_NEAR_CHARS:
            level_word, level_span, level_strong = match.group(1), match.span(1), True
    cut_level = level_word is not None

    if level_word is None and ts_near and ts_span:
        match = _AFTER_TS.match(head, ts_span[1])
        if match:
            level_word, level_span, level_strong = match.group(1), match.span(1), True
            cut_level = True
    if level_word is None:
        match = _LEAD.match(head)
        if match:
            level_word, level_span = match.group(1), match.span(1)
            cut_level = True
    if level_word is None:
        match = _KV.search(head)
        if match:
            level_word = match.group(1)  # read it, but leave the text alone

    cuts = []
    # Only cut the timestamp out when it is a plain prefix. In JSON and key=value
    # lines ("time":"...", time=...) it is a field, and removing it garbles the text.
    in_field = ts_span is not None and ts_span[0] > 0 and head[ts_span[0] - 1] in "\"'="
    if ts_near and ts_span and not in_field:
        cuts.append(ts_span)
    if cut_level and level_span:
        cuts.append(level_span)
    message = line
    for start, end in sorted(cuts, reverse=True):
        message = message[:start] + message[end:]
    message = _EMPTY_BRACKETS.sub("", message).lstrip(" -:|\t").strip()

    level = normalize_level(level_word) if level_word else "UNKNOWN"
    strong = ts_near or level_strong or line.startswith("{")
    return Header(timestamp, level, message[:MAX_MESSAGE_CHARS], strong)
