"""Settings read from environment variables.

Everything has a safe default so the app runs with no configuration.
Nothing here is secret: AI provider keys are never configured on the
server, users send their own key with each request.
"""

import os
from dataclasses import dataclass


def _int_env(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        value = int(raw)
    except ValueError:
        raise ValueError(f"{name} must be a whole number, got {raw!r}") from None
    if value <= 0:
        raise ValueError(f"{name} must be greater than 0, got {value}")
    return value


@dataclass(frozen=True)
class Settings:
    # Render sets PORT for us. 8000 is only the local default.
    port: int
    # Size and rate limits that protect a small free server.
    max_upload_bytes: int
    max_paste_bytes: int
    max_lines: int
    max_concurrent_analyses: int
    rate_limit_analyses_per_min: int
    rate_limit_ai_per_min: int
    # Websites allowed to call the API from a browser (for a separately hosted
    # landing page). Empty means same-origin only, which is the safe default.
    cors_origins: tuple[str, ...] = ()
    # True behind a proxy that sets X-Forwarded-For (Render does). Used to tell visitors apart.
    trust_proxy: bool = False


def _origins_env(name: str) -> tuple[str, ...]:
    raw = os.environ.get(name, "")
    origins = tuple(part.strip().rstrip("/") for part in raw.split(",") if part.strip())
    for origin in origins:
        if not origin.startswith(("http://", "https://")) or origin == "*":
            raise ValueError(f"{name} must be a comma-separated list of full origins, got {origin!r}")
    return origins


def _bool_env(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


def load_settings() -> Settings:
    return Settings(
        port=_int_env("PORT", 8000),
        max_upload_bytes=_int_env("LOGDOCTOR_MAX_UPLOAD_BYTES", 5 * 1024 * 1024),
        max_paste_bytes=_int_env("LOGDOCTOR_MAX_PASTE_BYTES", 1024 * 1024),
        max_lines=_int_env("LOGDOCTOR_MAX_LINES", 50_000),
        max_concurrent_analyses=_int_env("LOGDOCTOR_MAX_CONCURRENT", 2),
        rate_limit_analyses_per_min=_int_env("LOGDOCTOR_RATE_ANALYSES_PER_MIN", 20),
        rate_limit_ai_per_min=_int_env("LOGDOCTOR_RATE_AI_PER_MIN", 10),
        cors_origins=_origins_env("LOGDOCTOR_CORS_ORIGINS"),
        trust_proxy=_bool_env("LOGDOCTOR_TRUST_PROXY"),
    )
