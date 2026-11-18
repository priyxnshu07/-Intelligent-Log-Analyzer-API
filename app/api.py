"""HTTP endpoints. They are thin: check the input, call the engine, return the result."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request, Response
from starlette.concurrency import run_in_threadpool
from pydantic import ValidationError

from app import ai
from app.errors import ApiError
from app.ratelimit import limit_dependency
from app.ingest import ALLOWED_EXTENSIONS, check_extension, clean_filename, decode_log
from app.limits import format_bytes, read_limited_body, too_large
from app.ziputil import ZIP_SIGNATURE, read_zip
from app.schemas import AiRequest, AiResponse, ModelsRequest, ModelsResponse, AnalyzeResponse, SourceInfo, TextRequest
from logdoctor import analyze
from logdoctor.report import render_markdown


def no_store(response: Response) -> None:
    """Logs can be sensitive, so browsers and proxies must not keep the responses."""
    response.headers["Cache-Control"] = "no-store"


router = APIRouter(prefix="/api", dependencies=[Depends(no_store)])
analysis_limit = Depends(limit_dependency("analysis_limiter"))
ai_limit = Depends(limit_dependency("ai_limiter"))

_TEXT_BODY = {
    "requestBody": {
        "required": True,
        "content": {"application/json": {"schema": TextRequest.model_json_schema()}},
    }
}
_FILE_BODY = {
    "requestBody": {
        "required": True,
        "description": "The raw bytes of the log file. Content-Type is ignored.",
        "content": {"application/octet-stream": {"schema": {"type": "string", "format": "binary"}}},
    }
}


@router.get("/limits", summary="Limits and accepted file types")
def get_limits(request: Request) -> dict:
    settings = request.app.state.settings
    return {
        "max_upload_bytes": settings.max_upload_bytes,
        "max_paste_bytes": settings.max_paste_bytes,
        "max_lines": settings.max_lines,
        "allowed_extensions": list(ALLOWED_EXTENSIONS),
    }


@router.post(
    "/analyze/text",
    response_model=AnalyzeResponse,
    summary="Analyze pasted log text",
    dependencies=[analysis_limit],
    openapi_extra=_TEXT_BODY,
)
async def analyze_text(request: Request) -> AnalyzeResponse:
    settings = request.app.state.settings
    hint = f"Upload it as a file instead (up to {format_bytes(settings.max_upload_bytes)})."

    # JSON escaping can make text a bit longer, so the raw body gets some room.
    body = await read_limited_body(request, settings.max_paste_bytes * 2 + 4096, hint)
    try:
        payload = TextRequest.model_validate_json(body)
    except ValidationError as error:
        first = error.errors()[0]
        if first["type"] == "json_invalid":
            raise ApiError(400, "invalid_json", "The request body is not valid JSON.") from None
        raise ApiError(
            422, "invalid_request", "Send JSON like {\"text\": \"...your log...\"}."
        ) from None

    size = len(payload.text.encode("utf-8"))
    if size > settings.max_paste_bytes:
        raise too_large(settings.max_paste_bytes, hint)
    return await _analyze(request, payload.text, SourceInfo(
        type="paste", filename=None, bytes=size, encoding="utf-8", warnings=[]
    ))


@router.post(
    "/analyze/file",
    response_model=AnalyzeResponse,
    summary="Analyze an uploaded log file or a ZIP of logs",
    dependencies=[analysis_limit],
    openapi_extra=_FILE_BODY,
)
async def analyze_file(
    request: Request,
    filename: str | None = Query(None, max_length=255, description="Original file name, used to check the type."),
) -> AnalyzeResponse:
    settings = request.app.state.settings
    name = clean_filename(filename)
    check_extension(name)  # refuse unsupported types before reading the body

    data = await read_limited_body(request, settings.max_upload_bytes)
    if name and name.lower().endswith(".zip") or data.startswith(ZIP_SIGNATURE):
        if not data.startswith(ZIP_SIGNATURE):
            raise ApiError(400, "invalid_zip", "This is not a valid ZIP file.")
        zipped = await run_in_threadpool(read_zip, data)
        return await _analyze(request, zipped.text, SourceInfo(
            type="zip", filename=name, bytes=len(data), encoding="utf-8", warnings=zipped.warnings
        ))
    decoded = decode_log(data)
    return await _analyze(request, decoded.text, SourceInfo(
        type="file",
        filename=name,
        bytes=len(data),
        encoding=decoded.encoding,
        warnings=decoded.warnings,
    ))


_REPORT_BODY = {
    "requestBody": {
        "required": True,
        "description": "The JSON returned by /api/analyze/text or /api/analyze/file.",
        "content": {"application/json": {"schema": AnalyzeResponse.model_json_schema()}},
    }
}


@router.post("/report", dependencies=[analysis_limit], summary="Make a Markdown report from an analysis result", openapi_extra=_REPORT_BODY)
async def make_report(request: Request) -> Response:
    settings = request.app.state.settings
    body = await read_limited_body(request, settings.max_upload_bytes)
    try:
        data = AnalyzeResponse.model_validate_json(body)
    except ValidationError as error:
        if error.errors()[0]["type"] == "json_invalid":
            raise ApiError(400, "invalid_json", "The request body is not valid JSON.") from None
        raise ApiError(
            422, "invalid_request", "Send the JSON that /api/analyze/text or /api/analyze/file returned."
        ) from None
    markdown = render_markdown(data.analysis, data.source.filename)
    return Response(
        markdown,
        media_type="text/markdown; charset=utf-8",
        headers={
            "Content-Disposition": 'attachment; filename="log-report.md"',
            "Cache-Control": "no-store",
        },
    )


@router.post("/ai/models", response_model=ModelsResponse, summary="Chat models your own API key can use", dependencies=[ai_limit])
async def ai_models(request: Request) -> ModelsResponse:
    body = await read_limited_body(request, 4096)
    try:
        payload = ModelsRequest.model_validate_json(body)
    except ValidationError as error:
        if error.errors()[0]["type"] == "json_invalid":
            raise ApiError(400, "invalid_json", "The request body is not valid JSON.") from None
        raise ApiError(422, "invalid_request", 'Send {"provider": "groq|gemini|openrouter|mistral|openai|anthropic", "api_key": "..."}.') from None
    provider = ai.PROVIDERS[payload.provider]
    key = ai.check_key(payload.api_key.get_secret_value())
    models = await request.app.state.ai_gate.run(ai.list_models, provider, key, request.app.state.ai_transport)
    return ModelsResponse(provider=provider.id, default=provider.default_model, models=models)


@router.post("/ai/diagnose", response_model=AiResponse, summary="Optional AI explanation using your own API key", dependencies=[ai_limit])
async def ai_diagnose(request: Request) -> AiResponse:
    """Send a short excerpt of an analysis to the chosen provider with the caller's key.

    The key is used for this one call and dropped. It is never stored or logged.
    """
    settings = request.app.state.settings
    body = await read_limited_body(request, settings.max_upload_bytes)
    try:
        payload = AiRequest.model_validate_json(body)
    except ValidationError as error:
        if error.errors()[0]["type"] == "json_invalid":
            raise ApiError(400, "invalid_json", "The request body is not valid JSON.") from None
        raise ApiError(
            422,
            "invalid_request",
            "Send {\"provider\": \"groq|gemini|openrouter|mistral|openai|anthropic\", \"api_key\": \"...\", "
            "\"analysis\": <the JSON an analyze endpoint returned>}.",
        ) from None
    provider = ai.PROVIDERS[payload.provider]
    key = ai.check_key(payload.api_key.get_secret_value())
    model = ai.check_model(payload.model, provider)
    if not payload.analysis.analysis.groups:
        raise ApiError(400, "nothing_to_explain", "The analysis has no problem groups, so there is nothing to explain.")
    answer = await request.app.state.ai_gate.run(
        ai.ask, provider, key, model, payload.analysis.analysis, request.app.state.ai_transport
    )
    return AiResponse(**answer.__dict__)


async def _analyze(request: Request, text: str, source: SourceInfo) -> AnalyzeResponse:
    if not text.strip():
        raise ApiError(400, "empty_input", "No log text was received. Paste or upload a log.")
    settings = request.app.state.settings
    analysis = await request.app.state.gate.run(analyze, text, settings.max_lines)
    return AnalyzeResponse(source=source, analysis=analysis)
