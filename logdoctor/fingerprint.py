"""Decide when two log records are "the same error".

Ids, numbers, addresses and directories change between occurrences, so
they are masked before comparing. The rule is deterministic and explainable:
no AI is involved in grouping.
"""

from __future__ import annotations

import hashlib
import re

from logdoctor.models import LogEntry

_UUID = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)
_IPV4 = re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}(?::\d{1,5})?\b")
_HEX_ADDRESS = re.compile(r"\b0x[0-9a-fA-F]+\b")
_LONG_HEX = re.compile(r"\b(?=[0-9a-fA-F]*[a-fA-F])[0-9a-fA-F]{12,}\b")
_PATH = re.compile(r"(?:[A-Za-z]:)?(?:[\\/][^\s\\/:'\"()\[\]<>]+){2,}")
# Numbers, including ones glued to a unit ("2300ms", "2.5s"). Digits that are
# part of a name ("utf8", "http2", "base64") are left alone.
_NUMBER = re.compile(r"(?<![A-Za-z_\d])\d+(?:\.\d+)?")
_SPACES = re.compile(r"\s+")


def _mask_path(match: re.Match) -> str:
    last = re.split(r"[\\/]", match.group(0))[-1]
    return f"<path>/{last}"


def normalize_message(message: str) -> str:
    """Mask the parts of a message that change between occurrences."""
    text = _UUID.sub("<uuid>", message)
    text = _IPV4.sub("<ip>", text)
    text = _HEX_ADDRESS.sub("<hex>", text)
    text = _LONG_HEX.sub("<hex>", text)
    text = _PATH.sub(_mask_path, text)
    text = _NUMBER.sub("<n>", text)
    return _SPACES.sub(" ", text).strip()


def fingerprint(entry: LogEntry) -> tuple[str, str]:
    """Return (group id, masked pattern) for a log record."""
    exception = entry.exception_type or ""
    if entry.language == "python":
        # The exception and where it was raised matter, not the log wording.
        masked = normalize_message(entry.exception_message or "")
        parts = ["python", exception, masked, *entry.frames[-3:]]
        pattern = f"{exception}: {masked}" if exception and masked else (exception or masked)
    else:
        masked = normalize_message(entry.message)
        parts = [exception, masked]
        pattern = masked
    digest = hashlib.sha1("\x1f".join(parts).encode("utf-8", "replace")).hexdigest()
    return digest[:12], pattern


def title_for(entry: LogEntry) -> str:
    """Human-readable title using the real (unmasked) text of one occurrence."""
    if entry.language == "python" and entry.exception_type:
        detail = f": {entry.exception_message}" if entry.exception_message else ""
        return f"{entry.exception_type}{detail}"[:200]
    return entry.message[:200]
