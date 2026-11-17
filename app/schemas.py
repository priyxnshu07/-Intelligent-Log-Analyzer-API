"""Request and response shapes for the API."""

from __future__ import annotations

from pydantic import BaseModel

from logdoctor.models import Analysis


class TextRequest(BaseModel):
    text: str


class SourceInfo(BaseModel):
    type: str  # "paste" or "file"
    filename: str | None
    bytes: int
    encoding: str
    warnings: list[str]


class AnalyzeResponse(BaseModel):
    source: SourceInfo
    analysis: Analysis
