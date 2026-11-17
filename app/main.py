"""Universal Log Doctor: FastAPI entry point.

The app is stateless on purpose. It keeps nothing on disk and uses no
database, so it can run on a free host with an ephemeral filesystem.
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api import router as api_router
from app.config import Settings, load_settings
from app.errors import register_error_handlers
from app.limits import AnalysisGate

STATIC_DIR = Path(__file__).parent / "static"


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the app. Tests pass their own settings to use small limits."""
    settings = settings or load_settings()

    app = FastAPI(
        title="Universal Log Doctor",
        description="Paste or upload application logs and get a grouped, "
        "evidence-based diagnosis. Stateless: nothing is stored.",
        version="0.1.0",
    )
    app.state.settings = settings
    app.state.gate = AnalysisGate(settings.max_concurrent_analyses)

    register_error_handlers(app)
    app.include_router(api_router)

    @app.get("/health", summary="Health check for the hosting platform")
    def health() -> dict:
        return {"status": "ok"}

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    # Render gives us the port in $PORT. Locally it falls back to 8000.
    uvicorn.run("app.main:app", host="0.0.0.0", port=app.state.settings.port)
