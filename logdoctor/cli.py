"""Command-line interface: `logdoctor app.log`.

Works offline and sends nothing anywhere. Reads a file or standard input.
"""

from __future__ import annotations

import argparse
import sys

from logdoctor import __version__, analyze
from logdoctor.analyze import DEFAULT_MAX_LINES
from logdoctor.levels import LEVEL_RANK, rank
from logdoctor.models import Analysis

EXIT_OK = 0
EXIT_FAIL_ON = 1  # --fail-on threshold reached
EXIT_USAGE = 2  # bad input or arguments


def _when(value) -> str:
    return value.strftime("%Y-%m-%d %H:%M:%S") if value else "unknown time"


def format_report(result: Analysis, top: int = 10) -> str:
    s = result.summary
    lines = [f"Analyzed {s.lines_analyzed} of {s.total_lines} lines"]
    if s.truncated:
        lines.append("  (log was long: only the most recent lines were analyzed)")
    counts = ", ".join(f"{k} {v}" for k, v in s.level_counts.items() if v)
    lines.append(f"Levels: {counts or 'none found'}")
    if s.first_timestamp:
        lines.append(f"Time range: {_when(s.first_timestamp)} to {_when(s.last_timestamp)}")
    lines.append("")
    if not result.groups:
        lines.append("No warnings or errors found.")
        return "\n".join(lines)

    lines.append(f"{len(result.groups)} problem group(s), most severe first:")
    for i, g in enumerate(result.groups[:top], 1):
        lines.append(f"\n{i}. [{g.level}] {g.title}  (x{g.count})")
        lines.append(f"   first {_when(g.first_seen)}, last {_when(g.last_seen)}")
        shown = ", ".join(str(n) for n in g.lines)
        more = "..." if g.count > len(g.lines) else ""
        lines.append(f"   at line(s): {shown}{more}")
        if g.exception_type:
            lines.append(f"   exception: {g.exception_type}")
        for number, cause in enumerate(g.causes):
            if number == 0:
                lines.append(f"   probable cause: {cause.cause}")
                lines.extend(f"     {n}. {step}" for n, step in enumerate(cause.steps, 1))
            else:
                lines.append(f"   also possible: {cause.cause}")
    if any(g.causes for g in result.groups[:top]):
        lines.append("\nCauses are hints from fixed rules, not proof. Check them against the log.")
    if len(result.groups) > top:
        lines.append(f"\n... and {len(result.groups) - top} more (use --top or --json)")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="logdoctor",
        description="Group and explain the errors in a log file. Runs locally; nothing is uploaded.",
    )
    p.add_argument("file", nargs="?", default="-", help="log file, or - for standard input (default)")
    p.add_argument("--json", action="store_true", help="print the full analysis as JSON")
    p.add_argument("--top", type=int, default=10, help="groups to show in the text report (default 10)")
    p.add_argument("--max-lines", type=int, default=DEFAULT_MAX_LINES, help="analyze only the most recent N lines")
    p.add_argument(
        "--fail-on",
        choices=["warning", "error", "critical"],
        help="exit with status 1 if a group at or above this level is found (for CI)",
    )
    p.add_argument("--version", action="version", version=f"logdoctor {__version__}")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.top < 1 or args.max_lines < 1:
        print("logdoctor: --top and --max-lines must be at least 1", file=sys.stderr)
        return EXIT_USAGE
    try:
        if args.file == "-":
            text = sys.stdin.buffer.read().decode("utf-8", errors="replace")
        else:
            with open(args.file, "rb") as handle:
                text = handle.read().decode("utf-8", errors="replace")
    except OSError as error:
        print(f"logdoctor: cannot read {args.file}: {error.strerror}", file=sys.stderr)
        return EXIT_USAGE

    result = analyze(text, args.max_lines)
    print(result.to_json(indent=2) if args.json else format_report(result, args.top))

    if args.fail_on:
        threshold = LEVEL_RANK[args.fail_on.upper()]
        if any(rank(g.level) >= threshold for g in result.groups):
            return EXIT_FAIL_ON
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
