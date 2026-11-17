"""Public entry point: analyze(text) -> Analysis."""

from __future__ import annotations

from logdoctor.diagnose import diagnose_all
from logdoctor.entries import build_entries
from logdoctor.fingerprint import fingerprint, title_for
from logdoctor.levels import ERROR_RANK, WARNING_RANK, rank
from logdoctor.models import Analysis, ErrorGroup, LogEntry, Summary
from logdoctor.timeline import build_timeline

DEFAULT_MAX_LINES = 50_000
MAX_LINE_CHARS = 10_000  # longer lines are cut so one huge line cannot slow things down
MAX_EVIDENCE_LINES = 20


def analyze(text: str, max_lines: int = DEFAULT_MAX_LINES) -> Analysis:
    """Analyze log text.

    If there are more than `max_lines` lines, only the most recent ones are
    analyzed (the end of a log is usually the most useful part) and the
    summary says so. Line numbers always refer to the original input.
    """
    all_lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    if all_lines and all_lines[-1] == "":
        all_lines.pop()  # text ended with a newline

    total = len(all_lines)
    skipped = max(0, total - max_lines)
    lines = [line[:MAX_LINE_CHARS] for line in all_lines[skipped:]]

    entries = build_entries(lines, first_line_no=skipped + 1)
    groups = _group(entries)
    diagnose_all(groups)

    level_counts: dict[str, int] = {}
    for entry in entries:
        level_counts[entry.level] = level_counts.get(entry.level, 0) + 1
    level_counts = dict(sorted(level_counts.items(), key=lambda item: -rank(item[0])))

    stamps = [entry.timestamp for entry in entries if entry.timestamp]
    summary = Summary(
        total_lines=total,
        lines_analyzed=len(lines),
        truncated=skipped > 0,
        entries=len(entries),
        level_counts=level_counts,
        error_count=sum(1 for e in entries if rank(e.level) >= ERROR_RANK),
        warning_count=sum(1 for e in entries if rank(e.level) == WARNING_RANK),
        group_count=len(groups),
        first_timestamp=min(stamps) if stamps else None,
        last_timestamp=max(stamps) if stamps else None,
        languages=sorted({e.language for e in entries if e.language}),
    )
    return Analysis(summary=summary, groups=groups, timeline=build_timeline(entries))


def _group(entries: list[LogEntry]) -> list[ErrorGroup]:
    """Group warnings and errors that are the same problem."""
    groups: dict[str, ErrorGroup] = {}

    for entry in entries:
        if rank(entry.level) < WARNING_RANK:
            continue
        group_id, pattern = fingerprint(entry)
        group = groups.get(group_id)
        if group is None:
            groups[group_id] = ErrorGroup(
                id=group_id,
                level=entry.level,
                title=title_for(entry),
                pattern=pattern,
                exception_type=entry.exception_type,
                language=entry.language,
                count=1,
                first_seen=entry.timestamp,
                last_seen=entry.timestamp,
                first_line=entry.line,
                last_line=entry.line,
                lines=[entry.line],
                frames=entry.frames[-5:],
                sample=entry.text,
            )
            continue

        group.count += 1
        group.last_line = entry.line
        if len(group.lines) < MAX_EVIDENCE_LINES:
            group.lines.append(entry.line)
        if rank(entry.level) > rank(group.level):
            group.level = entry.level
        if entry.timestamp:
            if group.first_seen is None or entry.timestamp < group.first_seen:
                group.first_seen = entry.timestamp
            if group.last_seen is None or entry.timestamp > group.last_seen:
                group.last_seen = entry.timestamp

    return sorted(groups.values(), key=lambda g: (-rank(g.level), -g.count, g.first_line))
