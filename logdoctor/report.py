"""Turn an analysis into a Markdown report you can save, share or attach to a ticket.

Log text is untrusted and ends up inside a Markdown file that a viewer may
render, so it is escaped when shown inline and placed in code fences (longer
than any run of backticks inside) when shown as a block. The output has no
clock time in it, so the same analysis always gives the same report.
"""

from __future__ import annotations

import re
from datetime import datetime

from logdoctor.models import Analysis, ErrorGroup

MAX_DETAILED_GROUPS = 50
MAX_SAMPLE_CHARS = 2000
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_SPECIAL = re.compile(r"([\\`*_\[\]<>|#~&])")
_BACKTICKS = re.compile(r"`+")


def _inline(text: str, limit: int = 300) -> str:
    """Text for a heading or sentence: one line, with Markdown characters escaped."""
    text = " ".join(_CONTROL.sub("", text).split())[:limit]
    return _SPECIAL.sub(r"\\\1", text)


def _block(text: str) -> str:
    """Text as a code block, using a fence that the text cannot close."""
    text = _CONTROL.sub("", text)
    if len(text) > MAX_SAMPLE_CHARS:
        text = text[:MAX_SAMPLE_CHARS] + "\n... [shortened]"
    longest = max((len(run) for run in _BACKTICKS.findall(text)), default=0)
    fence = "`" * max(3, longest + 1)
    return f"{fence}text\n{text}\n{fence}"


def _when(value: datetime | None) -> str:
    return value.strftime("%Y-%m-%d %H:%M:%S") if value else "unknown"


def _group_section(number: int, group: ErrorGroup) -> list[str]:
    out = [f"### {number}. [{group.level}] {_inline(group.title, 200)}", ""]
    lines = ", ".join(str(n) for n in group.lines) + (", ..." if group.count > len(group.lines) else "")
    out.append(f"- Seen **{group.count}** time(s), first {_when(group.first_seen)}, last {_when(group.last_seen)}")
    out.append(f"- Log lines: {lines}")
    if group.exception_type:
        out.append(f"- Exception: {_inline(group.exception_type, 200)}")
    if group.language:
        out.append(f"- Language: {_inline(group.language, 40)}")
    if group.frames:
        out.append(f"- Innermost frames: {_inline(', '.join(group.frames[-3:]), 400)}")
    out.append("")

    if group.causes:
        out.append("**Probable causes** (hints from fixed rules, not proof)")
        out.append("")
        for index, cause in enumerate(group.causes, 1):
            out.append(f"{index}. **{_inline(cause.cause)}**. {_inline(cause.explanation, 500)}")
            out.append(f"   - Matched \"{_inline(cause.matched, 120)}\" in the {_inline(cause.where, 40)}.")
            for step_number, step in enumerate(cause.steps, 1):
                out.append(f"   - Step {step_number}: {_inline(step, 500)}")
        out.append("")

    out.append("First occurrence:")
    out.append("")
    out.append(_block(group.sample))
    out.append("")
    return out


def render_markdown(analysis: Analysis, source_name: str | None = None) -> str:
    s = analysis.summary
    out = ["# Log diagnosis report", ""]
    out.append("Made by Universal Log Doctor. The log was analyzed in memory and not stored.")
    out.append("")

    out += ["## Summary", ""]
    if source_name:
        out.append(f"- Source: {_inline(source_name, 200)}")
    out.append(f"- Lines analyzed: {s.lines_analyzed} of {s.total_lines}" + (" (only the most recent lines)" if s.truncated else ""))
    counts = ", ".join(f"{level} {count}" for level, count in s.level_counts.items() if count)
    out.append(f"- Records by level: {counts or 'none found'}")
    out.append(f"- Errors: {s.error_count}, warnings: {s.warning_count}, problem groups: {s.group_count}")
    if s.first_timestamp:
        out.append(f"- Time range: {_when(s.first_timestamp)} to {_when(s.last_timestamp)} (times as found in the log, converted to UTC when it gave a zone)")
    if s.languages:
        out.append(f"- Languages detected: {', '.join(_inline(name, 40) for name in s.languages)}")
    out.append("")

    buckets = [b for b in analysis.timeline.buckets if b.errors or b.warnings]
    if buckets:
        peak = max(buckets, key=lambda b: (b.errors, b.warnings))
        out += ["## Timeline", ""]
        out.append(f"- Busiest period: starting {_when(peak.start)} (errors: {peak.errors}, warnings: {peak.warnings}; steps of {analysis.timeline.bucket_seconds} seconds)")
        out.append(f"- First problem: {_when(buckets[0].start)}, last problem: {_when(buckets[-1].start)}")
        out.append("")

    out += ["## Problems", ""]
    if not analysis.groups:
        out += ["No warnings or errors were found.", ""]
    for number, group in enumerate(analysis.groups[:MAX_DETAILED_GROUPS], 1):
        out += _group_section(number, group)
    hidden = len(analysis.groups) - MAX_DETAILED_GROUPS
    if hidden > 0:
        out += [f"...and {hidden} more group(s) not shown in this report.", ""]
    if s.groups_omitted:
        out += [f"{s.groups_omitted} further group(s) were found but not returned by the analysis.", ""]

    out += [
        "## About this report",
        "",
        "- Errors are grouped by pattern: ids, numbers and paths are ignored when deciding that two errors are the same problem.",
        "- Probable causes come from a fixed list of rules. They are common explanations, not a diagnosis of your system.",
        "- Only the most recent lines of a long log are analyzed, and some formats are not read (see the project README).",
        "",
    ]
    return "\n".join(out)
