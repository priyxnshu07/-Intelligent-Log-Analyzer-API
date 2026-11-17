import pytest
from fastapi.testclient import TestClient

from app.config import load_settings
from app.main import app

client = TestClient(app)


def test_health_returns_ok():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_index_page_is_served():
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Universal Log Doctor" in response.text


def test_unknown_route_is_404():
    assert client.get("/does-not-exist").status_code == 404


def test_old_database_endpoints_are_gone():
    # The app is stateless now, nothing should accept stored logs.
    assert client.post("/ingest/", json={}).status_code == 404
    assert client.get("/query/").status_code == 404
    assert client.get("/summary/").status_code == 404


def test_settings_defaults(monkeypatch):
    for name in (
        "PORT",
        "LOGDOCTOR_MAX_UPLOAD_BYTES",
        "LOGDOCTOR_MAX_PASTE_BYTES",
        "LOGDOCTOR_MAX_LINES",
        "LOGDOCTOR_MAX_CONCURRENT",
        "LOGDOCTOR_RATE_ANALYSES_PER_MIN",
        "LOGDOCTOR_RATE_AI_PER_MIN",
    ):
        monkeypatch.delenv(name, raising=False)
    s = load_settings()
    assert s.port == 8000
    assert s.max_upload_bytes == 5 * 1024 * 1024
    assert s.max_paste_bytes == 1024 * 1024
    assert s.max_lines == 50_000
    assert s.max_concurrent_analyses == 2
    assert s.rate_limit_analyses_per_min == 20
    assert s.rate_limit_ai_per_min == 5


def test_settings_use_render_port(monkeypatch):
    monkeypatch.setenv("PORT", "10000")
    assert load_settings().port == 10000


def test_settings_can_be_overridden(monkeypatch):
    monkeypatch.setenv("LOGDOCTOR_MAX_LINES", "1234")
    assert load_settings().max_lines == 1234


@pytest.mark.parametrize("bad", ["abc", "0", "-5"])
def test_settings_reject_bad_values(monkeypatch, bad):
    monkeypatch.setenv("LOGDOCTOR_MAX_LINES", bad)
    with pytest.raises(ValueError):
        load_settings()


def test_static_assets_served():
    for path in ("/static/app.js", "/static/style.css", "/static/samples/python-web-app.txt"):
        assert client.get(path).status_code == 200, path


def test_sample_log_has_problems():
    from logdoctor import analyze

    text = client.get("/static/samples/python-web-app.txt").text
    result = analyze(text)
    assert result.summary.group_count == 4
    assert result.summary.languages == ["python"]


def test_frontend_never_uses_unsafe_html_apis():
    # Log text and file names are untrusted, so they may only be shown as text.
    source = client.get("/static/app.js").text
    for banned in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval("):
        assert banned not in source, banned
