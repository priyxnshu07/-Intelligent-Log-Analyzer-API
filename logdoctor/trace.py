"""What a language-specific detector returns for one log record."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TraceError:
    exception_type: str | None
    exception_message: str | None
    frames: list[str] = field(default_factory=list)  # "file:function", innermost last
