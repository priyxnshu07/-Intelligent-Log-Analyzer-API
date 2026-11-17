import pytest

from logdoctor.entries import build_entries
from logdoctor.fingerprint import fingerprint, normalize_message, title_for


@pytest.mark.parametrize(
    "raw, masked",
    [
        ("user 12345 not found", "user <n> not found"),
        ("took 2.5s", "took <n>s"),
        ("Slow query took 2300ms", "Slow query took <n>ms"),
        ("retry 3/5", "retry <n>/<n>"),
        ("decoded as utf8 with http2", "decoded as utf8 with http2"),
        ("connect to 10.0.0.5:5432 failed", "connect to <ip> failed"),
        ("job 9f1c2e3a-1111-4222-8333-444455556666 failed", "job <uuid> failed"),
        ("segfault at 0x7ffd1234abcd", "segfault at <hex>"),
        ("commit 3f2a9c1b7d4e5f60 broke", "commit <hex> broke"),
        ("cannot open /var/lib/app/data/file.db", "cannot open <path>/file.db"),
        (r"cannot open C:\Users\me\app\file.db", "cannot open <path>/file.db"),
        ("lots   of    spaces", "lots of spaces"),
        ("KeyError: 'user_id'", "KeyError: 'user_id'"),  # names are kept, only values masked
    ],
)
def test_normalize_message(raw, masked):
    assert normalize_message(raw) == masked


def entry_for(text):
    return build_entries(text.strip("\n").split("\n"))[0]


def test_same_error_with_different_values_gets_the_same_id():
    a = entry_for("2026-11-18 01:00:00 ERROR db could not connect to 10.0.0.5:5432 after 3 retries")
    b = entry_for("2026-11-18 02:30:00 ERROR db could not connect to 10.0.0.9:5432 after 5 retries")
    assert fingerprint(a)[0] == fingerprint(b)[0]


def test_durations_with_units_do_not_split_a_group():
    a = entry_for("2026-11-18 01:00:00 WARN db Slow query took 2300ms")
    b = entry_for("2026-11-18 01:00:05 WARN db Slow query took 900ms")
    assert fingerprint(a)[0] == fingerprint(b)[0]


def test_different_messages_get_different_ids():
    a = entry_for("2026-11-18 01:00:00 ERROR db connection refused")
    b = entry_for("2026-11-18 01:00:00 ERROR db connection reset")
    assert fingerprint(a)[0] != fingerprint(b)[0]


TRACE = """2026-11-18 01:00:00 ERROR app boom
Traceback (most recent call last):
  File "/srv/{file}", line {line}, in {func}
    x = d["k"]
KeyError: 'k'"""


def test_python_errors_group_by_exception_and_location_not_by_log_wording():
    a = entry_for(TRACE.format(file="views.py", line=10, func="get"))
    b = entry_for(
        TRACE.format(file="views.py", line=99, func="get").replace("ERROR app boom", "ERROR other text")
    )
    assert fingerprint(a)[0] == fingerprint(b)[0]  # line number and log wording do not matter


def test_same_exception_from_different_functions_is_a_different_problem():
    a = entry_for(TRACE.format(file="views.py", line=10, func="get"))
    b = entry_for(TRACE.format(file="views.py", line=10, func="post"))
    assert fingerprint(a)[0] != fingerprint(b)[0]


def test_python_pattern_and_title():
    entry = entry_for(TRACE.format(file="views.py", line=10, func="get"))
    assert fingerprint(entry)[1] == "KeyError: 'k'"
    assert title_for(entry) == "KeyError: 'k'"


def test_title_uses_the_unmasked_message_for_plain_errors():
    entry = entry_for("2026-11-18 01:00:00 ERROR db user 42 not found")
    assert title_for(entry) == "db user 42 not found"
    assert fingerprint(entry)[1] == "db user <n> not found"


def test_id_is_short_and_stable():
    entry = entry_for("2026-11-18 01:00:00 ERROR db down")
    first = fingerprint(entry)[0]
    assert len(first) == 12
    assert fingerprint(entry)[0] == first
