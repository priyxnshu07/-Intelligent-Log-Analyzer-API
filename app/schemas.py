"""Request and response shapes for the API."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, SecretStr

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


class AiRequest(BaseModel):
    provider: Literal["groq", "openai", "anthropic"]
    api_key: SecretStr  # hidden from repr and logs; used for one call, never stored
    model: str | None = None
    analysis: AnalyzeResponse  # the JSON an analyze endpoint returned


class AiResponse(BaseModel):
    provider: str
    model: str
    text: str
    groups_sent: int
    characters_sent: int


class ModelsRequest(BaseModel):
    provider: Literal["groq", "openai", "anthropic"]
    api_key: SecretStr


class ModelsResponse(BaseModel):
    provider: str
    default: str
    models: list[str]
