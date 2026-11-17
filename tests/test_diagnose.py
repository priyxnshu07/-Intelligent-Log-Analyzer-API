import time

import pytest

from logdoctor import analyze
from logdoctor.diagnose import MAX_CAUSES, MAX_DIAGNOSED_GROUPS, diagnose
from logdoctor.models import ErrorGroup
from logdoctor.rules import RULES


def group(title, exception_type=None, sample=None, language=None):
    return ErrorGroup(
        id="x", level="ERROR", title=title, pattern=title, exception_type=exception_type,
        language=language, count=1, first_seen=None, last_seen=None, first_line=1, last_line=1,
        lines=[1], frames=[], sample=title if sample is None else sample,
    )


def ids(g):
    return [c.id for c in diagnose(g)]


# One real-looking message per rule. A test below fails if a rule has no example.
EXAMPLES = [
    ("cpp-use-after-free", "AddressSanitizer: heap-use-after-free", "AddressSanitizer", "cpp"),
    ("cpp-buffer-overflow", "AddressSanitizer: heap-buffer-overflow", "AddressSanitizer", "cpp"),
    ("cpp-data-race", "ThreadSanitizer: data race", "ThreadSanitizer", "cpp"),
    ("cpp-uncaught-exception", "terminate called after throwing an instance of 'Foo'", None, "cpp"),
    ("cpp-assertion", "assertion: budget > 0 (in void tick())", "assertion", "cpp"),
    ("cpp-segfault", "SIGSEGV: Segmentation fault", "SIGSEGV", "cpp"),
    ("go-concurrent-map", "fatal error: concurrent map writes", "fatal error", "go"),
    ("go-deadlock", "fatal error: all goroutines are asleep - deadlock!", "fatal error", "go"),
    ("go-nil-map", "panic: assignment to entry in nil map", "panic", "go"),
    ("out-of-memory", "java.lang.OutOfMemoryError: Java heap space", None, None),
    ("stack-overflow", "RecursionError: maximum recursion depth exceeded", None, None),
    ("disk-full", "OSError: [Errno 28] No space left on device", None, None),
    ("too-many-open-files", "Error: EMFILE: too many open files, open '/a'", None, None),
    ("address-in-use", "Error: listen EADDRINUSE: address already in use :::3000", None, None),
    ("pool-exhausted", "FATAL: remaining connection slots are reserved", None, None),
    ("connection-refused", "Error: connect ECONNREFUSED 127.0.0.1:5432", None, None),
    ("dns-failure", "Error: getaddrinfo ENOTFOUND api.example.com", None, None),
    ("ssl-error", "SSL: CERTIFICATE_VERIFY_FAILED", None, None),
    ("connection-reset", "Error: read ECONNRESET", None, None),
    ("http-5xx", "502 Bad Gateway from upstream", None, None),
    ("rate-limited", "HTTP 429 returned by provider", None, None),
    ("timeout", "context deadline exceeded", None, None),
    ("cannot-connect", "could not connect to server", None, None),
    ("null-reference", "TypeError: Cannot read properties of undefined (reading 'id')", None, None),
    ("missing-key-or-index", "KeyError: 'user_id'", None, None),
    ("bad-input", "ValueError: invalid literal for int() with base 10: 'abc'", None, None),
    ("parse-error", "json.decoder.JSONDecodeError: Expecting value", None, None),
    ("missing-module", "ModuleNotFoundError: No module named 'requests'", None, None),
    ("file-not-found", "FileNotFoundError: [Errno 2] No such file or directory: 'a.csv'", None, None),
    ("permission-denied", "PermissionError: [Errno 13] Permission denied", None, None),
    ("auth-failure", "password authentication failed for user app", None, None),
    ("missing-config", "required environment variable DATABASE_URL is not set", None, None),
    ("deadlock-or-lock", "Deadlock found when trying to get lock", None, None),
    ("unhandled-rejection", "UnhandledPromiseRejection: This error originated", None, "javascript"),
    ("slow-operation", "Slow query took 2300ms", None, None),
]


@pytest.mark.parametrize("rule_id, title, exception_type, language", EXAMPLES)
def test_each_rule_fires_on_its_example(rule_id, title, exception_type, language):
    assert rule_id in ids(group(title, exception_type, language=language))


def test_every_rule_has_an_example():
    assert {rule.id for rule in RULES} == {example[0] for example in EXAMPLES}


def test_rules_are_well_formed():
    seen = set()
    for rule in RULES:
        assert rule.id not in seen, rule.id
        seen.add(rule.id)
        assert rule.cause and rule.explanation and len(rule.steps) >= 2, rule.id
        assert all(step.strip() for step in rule.steps), rule.id


def test_language_specific_rules_stay_in_their_language():
    assert "go-deadlock" not in ids(group("all goroutines are asleep - deadlock!", language="python"))
    assert "cpp-assertion" not in ids(group("assertion failed in test", language="python"))
    assert "cpp-segfault" not in ids(group("SIGSEGV received", language="java"))


def test_message_match_ranks_above_stack_trace_match():
    # A KeyError raised in a file called timeout_handler.py is not a timeout.
    sample = "Traceback (most recent call last):\n  File \"/srv/timeout_handler.py\", line 4, in run\nKeyError: 'a'"
    causes = diagnose(group("KeyError: 'a'", "KeyError", sample, "python"))
    assert [c.id for c in causes][0] == "missing-key-or-index"
    assert causes[0].where == "message"
    weak = [c for c in causes if c.where == "stack trace"]
    assert [c.id for c in weak] == ["timeout"]


def test_matched_text_and_steps_are_returned():
    cause = diagnose(group("Error: connect ECONNREFUSED 127.0.0.1:5432"))[0]
    assert cause.id == "connection-refused"
    assert cause.matched == "ECONNREFUSED"
    assert len(cause.steps) >= 3


def test_steps_are_copies_not_the_rule_data():
    first = diagnose(group("KeyError: 'a'"))[0]
    first.steps.append("changed")
    again = diagnose(group("KeyError: 'a'"))[0]
    assert "changed" not in again.steps


def test_at_most_three_causes():
    noisy = group("timeout: connection refused, out of memory, KeyError, permission denied, disk full")
    assert len(diagnose(noisy)) == MAX_CAUSES


def test_unknown_problem_gets_no_causes():
    assert diagnose(group("payment declined for order 5521")) == []


def test_numbers_alone_do_not_trigger_http_rules():
    assert diagnose(group("processed 401 records and 429 items")) == []
    assert "auth-failure" in ids(group("request returned HTTP 401"))


def test_analysis_attaches_causes():
    result = analyze("2024-05-01 10:00:00 ERROR Error: connect ECONNREFUSED 127.0.0.1:5432\n")
    assert result.groups[0].causes[0].id == "connection-refused"
    assert result.to_dict()["groups"][0]["causes"][0]["steps"]


def test_only_the_top_groups_are_diagnosed():
    lines = [f"2024-05-01 10:00:00 ERROR unique failure number {i} {'abc' * i}x ECONNREFUSED" for i in range(1, MAX_DIAGNOSED_GROUPS + 21)]
    groups = analyze("\n".join(lines)).groups
    assert len(groups) == MAX_DIAGNOSED_GROUPS + 20
    assert all(g.causes for g in groups[:MAX_DIAGNOSED_GROUPS])
    assert all(not g.causes for g in groups[MAX_DIAGNOSED_GROUPS:])


def test_hostile_text_is_fast():
    nasty = [
        "assertion " + "x" * 100_000,
        "502 " + " " * 100_000 + "bad",
        "connect to " + "a" * 100_000 + " failed",
        "required " + "environment variable " * 20_000,
        "HTTP " + " " * 100_000 + "429",
    ]
    start = time.perf_counter()
    for text in nasty:
        diagnose(group(text, sample=text, language="cpp"))
    assert time.perf_counter() - start < 1.0
