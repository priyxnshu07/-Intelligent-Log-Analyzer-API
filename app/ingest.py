"""Checks and decoding for log text that arrives from a user."""

from __future__ import annotations

import codecs
import re
from dataclasses import dataclass, field

from app.errors import ApiError

ALLOWED_EXTENSIONS = (".txt", ".log", ".json", ".jsonl", ".ndjson", ".csv")

_NAME_PARTS = re.compile(r"[\\/]")
_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")
_BINARY_SIGNATURES = (
    (b"PK\x03\x04", "ZIP files are not supported yet. Extract the log file and upload that."),
    (b"\x1f\x8b", "Compressed (.gz) files are not supported. Decompress the file first."),
    (b"%PDF", "This looks like a PDF, not a text log."),
    (b"\x89PNG", "This looks like an image, not a text log."),
)


@dataclass
class DecodedLog:
    text: str
    encoding: str
    warnings: list[str] = field(default_factory=list)


def clean_filename(name: str | None) -> str | None:
    """Keep only the file name, without folders or control characters."""
    if not name:
        return None
    base = _NAME_PARTS.split(name)[-1]
    base = _CONTROL_CHARS.sub("", base).strip()[:255]
    return base or None


def check_extension(filename: str | None) -> None:
    """Reject file types we do not read. A missing extension is fine."""
    if not filename:
        return
    suffixes = [part.lower() for part in _suffixes(filename)]
    while suffixes and suffixes[-1][1:].isdigit():  # rotated logs: app.log.1
        suffixes.pop()
    if not suffixes or suffixes[-1] in ALLOWED_EXTENSIONS:
        return
    allowed = ", ".join(ALLOWED_EXTENSIONS)
    raise ApiError(
        415,
        "unsupported_file_type",
        f"Files of type '{suffixes[-1]}' are not supported. Upload one of {allowed}, "
        "or paste the log text.",
    )


def _suffixes(filename: str) -> list[str]:
    parts = filename.split(".")
    return ["." + part for part in parts[1:] if part] if len(parts) > 1 else []


def decode_log(data: bytes) -> DecodedLog:
    """Turn uploaded bytes into text, refusing things that are clearly not text logs."""
    if data.startswith(codecs.BOM_UTF8):
        encoding = "utf-8-sig"
    elif data.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        encoding = "utf-16"
    else:
        encoding = "utf-8"
        for signature, message in _BINARY_SIGNATURES:
            if data.startswith(signature):
                raise ApiError(415, "unsupported_file_type", message)
        if b"\x00" in data[:8192]:
            raise ApiError(
                415,
                "binary_file",
                "This looks like a binary file, not a text log. "
                "If it is UTF-16 text, save it as UTF-8 and try again.",
            )

    text = data.decode(encoding, errors="replace")
    warnings = []
    replaced = text.count("�")
    if replaced:
        warnings.append(
            f"{replaced} character(s) could not be read as {encoding} and were replaced."
        )
    return DecodedLog(text, encoding, warnings)
