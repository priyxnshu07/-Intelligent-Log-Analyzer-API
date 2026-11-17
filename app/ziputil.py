"""Reading logs out of an uploaded ZIP, safely.

Nothing is written to disk: members are read straight into memory, so a
hostile file name cannot escape into the filesystem. The limits below stop
zip bombs: sizes are counted while reading and never taken on trust from the
file's own headers.
"""

from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass

from app.errors import ApiError
from app.ingest import ALLOWED_EXTENSIONS, decode_log

ZIP_SIGNATURE = b"PK\x03\x04"
MAX_ENTRIES_SCANNED = 1000
MAX_FILES_READ = 20
MAX_MEMBER_BYTES = 10 * 1024 * 1024
MAX_TOTAL_BYTES = 20 * 1024 * 1024


@dataclass
class ZipLogs:
    text: str
    files: list[str]
    warnings: list[str]


def _bad(message: str, status: int = 400, code: str = "invalid_zip") -> ApiError:
    return ApiError(status, code, message)


def _usable_name(name: str) -> bool:
    if not name or name.endswith("/") or "\\" in name or name.startswith("/"):
        return False
    if any(part in ("..", "") for part in name.split("/")):
        return False
    if any(ord(c) < 32 for c in name):
        return False
    base = name.rsplit("/", 1)[-1].lower()
    if base.startswith(".") or "__macosx" in name.lower():
        return False
    suffixes = ["." + p for p in base.split(".")[1:] if p]
    while suffixes and suffixes[-1][1:].isdigit():  # app.log.1
        suffixes.pop()
    return not suffixes or suffixes[-1] in ALLOWED_EXTENSIONS and suffixes[-1] != ".zip"


def read_zip(data: bytes) -> ZipLogs:
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
        infos = archive.infolist()
    except (zipfile.BadZipFile, ValueError, OSError, NotImplementedError):
        raise _bad("This is not a valid ZIP file.") from None
    if len(infos) > MAX_ENTRIES_SCANNED:
        raise _bad(f"The ZIP has more than {MAX_ENTRIES_SCANNED} entries. Zip only the log files you need.", 413, "zip_too_many_files")

    texts: list[str] = []
    used: list[str] = []
    warnings: list[str] = []
    skipped = 0
    total = 0
    for info in sorted((i for i in infos if not i.is_dir()), key=lambda i: i.filename):
        if not _usable_name(info.filename):
            skipped += 1
            continue
        if info.flag_bits & 0x1:
            raise _bad("The ZIP is password protected. Remove the password and try again.", 415, "zip_encrypted")
        if len(used) >= MAX_FILES_READ:
            warnings.append(f"Only the first {MAX_FILES_READ} log files in the ZIP were read.")
            break
        allowance = min(MAX_MEMBER_BYTES, MAX_TOTAL_BYTES - total)
        try:
            with archive.open(info) as member:
                raw = member.read(allowance + 1)  # real size, not the one the header claims
        except (zipfile.BadZipFile, NotImplementedError, RuntimeError, OSError, EOFError, ValueError):
            raise _bad("The ZIP could not be read. It may be damaged or use an unsupported method.") from None
        if len(raw) > allowance:
            raise _bad(
                "The files inside this ZIP are too large when unpacked "
                f"(limit {MAX_MEMBER_BYTES // (1024 * 1024)} MB per file, {MAX_TOTAL_BYTES // (1024 * 1024)} MB in total).",
                413, "zip_too_large",
            )
        total += len(raw)
        try:
            decoded = decode_log(raw)
        except ApiError:
            skipped += 1
            continue
        texts.append(decoded.text.rstrip("\n"))
        used.append(info.filename)
        warnings.extend(f"{info.filename}: {w}" for w in decoded.warnings)

    if not used:
        raise _bad(
            "No log files were found in the ZIP. It should contain files ending in "
            + ", ".join(e for e in ALLOWED_EXTENSIONS if e != ".zip") + ".",
            415, "zip_no_logs",
        )
    if skipped:
        warnings.append(f"{skipped} other file(s) in the ZIP were skipped (not log files).")
    listing = ", ".join(used[:5]) + (f" and {len(used) - 5} more" if len(used) > 5 else "")
    warnings.insert(0, f"Read {len(used)} file(s) from the ZIP, joined in name order: {listing}.")
    return ZipLogs("\n".join(texts) + "\n", used, warnings)
