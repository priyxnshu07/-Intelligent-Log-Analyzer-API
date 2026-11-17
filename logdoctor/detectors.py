"""Try every language detector on a piece of text."""

from __future__ import annotations

from logdoctor.cpptrace import detect_cpp
from logdoctor.gotrace import detect_go
from logdoctor.javatrace import detect_java
from logdoctor.nodetrace import detect_node
from logdoctor.pytrace import detect_python
from logdoctor.trace import TraceError

# Order matters: the first detector that finds something wins.
_DETECTORS = (
    ("python", detect_python),
    ("java", detect_java),
    ("javascript", detect_node),
    ("go", detect_go),
    ("cpp", detect_cpp),
)


def detect_trace(text: str) -> tuple[str, TraceError] | None:
    """Return (language, error) for the first language that recognizes `text`."""
    for language, detect in _DETECTORS:
        found = detect(text)
        if found is not None:
            return language, found
    return None
