"""Universal Log Doctor: FastAPI entry point.

The app is stateless on purpose. It keeps nothing on disk and uses no
database, so it can run on a free host with an ephemeral filesystem.
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import load_settings

STATIC_DIR = Path(__file__).parent / "static"

settings = load_settings()

app = FastAPI(
    title="Universal Log Doctor",
    description="Paste or upload application logs and get a grouped, "
    "evidence-based diagnosis. Stateless: nothing is stored.",
    version="0.1.0",
)


@app.get("/health", summary="Health check for the hosting platform")
def health() -> dict:
    return {"status": "ok"}


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


if __name__ == "__main__":
    import uvicorn

    # Render gives us the port in $PORT. Locally it falls back to 8000.
    uvicorn.run("app.main:app", host="0.0.0.0", port=settings.port)
