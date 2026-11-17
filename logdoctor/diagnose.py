"""Match error groups against the known rules.

The result is a list of probable causes. They are hints from a fixed rule
list, so the same log always gives the same answer and no AI is involved.
"""

from __future__ import annotations

import re

from logdoctor.models import ErrorGroup, ProbableCause
from logdoctor.rules import RULES

MAX_CAUSES = 3  # per group
MAX_DIAGNOSED_GROUPS = 100  # a log of thousands of unique errors must stay fast
HEAD_CHARS = 600  # exception type and title
BODY_CHARS = 1500  # start of the full text, where the stack trace is
MATCH_CHARS = 100

_COMPILED = tuple((rule, re.compile(rule.pattern, re.IGNORECASE)) for rule in RULES)


def diagnose(group: ErrorGroup) -> list[ProbableCause]:
    """Probable causes for one group, best first. Empty when no rule matches.

    A match in the exception type or title is stronger than one that only
    appears in the stack trace (a file called timeout.py is not a timeout), so
    those come first.
    """
    head = f"{group.exception_type or ''}\n{group.title}"[:HEAD_CHARS]
    body = group.sample[:BODY_CHARS]

    strong: list[ProbableCause] = []
    weak: list[ProbableCause] = []
    for rule, pattern in _COMPILED:
        if rule.languages and group.language not in rule.languages:
            continue
        found = pattern.search(head)
        bucket, where = strong, "message"
        if not found:
            found = pattern.search(body)
            bucket, where = weak, "stack trace"
        if found:
            bucket.append(
                ProbableCause(
                    id=rule.id,
                    cause=rule.cause,
                    explanation=rule.explanation,
                    steps=list(rule.steps),
                    matched=" ".join(found.group(0).split())[:MATCH_CHARS],
                    where=where,
                )
            )
    return (strong + weak)[:MAX_CAUSES]


def diagnose_all(groups: list[ErrorGroup]) -> None:
    """Fill in `causes` for the most important groups (the list is already sorted)."""
    for group in groups[:MAX_DIAGNOSED_GROUPS]:
        group.causes = diagnose(group)
