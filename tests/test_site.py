import importlib.util
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import load_settings
from app.main import create_app

ROOT = Path(__file__).parent.parent


def load_build_site():
    spec = importlib.util.spec_from_file_location("build_site", ROOT / "scripts/build_site.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.build_site


def test_build_site_layout(tmp_path):
    out = tmp_path / "site"
    load_build_site()(out, "https://api.example.com/")
    assert (out / "index.html").exists()
    assert (out / "static/app.js").exists()
    assert (out / ".nojekyll").exists()
    assert not (out / "static/index.html").exists()
    assert (out / "static/config.js").read_text() == 'window.LOGDOCTOR_API = "https://api.example.com";\n'


def test_build_site_rejects_bad_url(tmp_path):
    with pytest.raises(ValueError):
        load_build_site()(tmp_path / "s", "api.example.com")


def test_cors_off_by_default():
    client = TestClient(create_app(load_settings()))
    r = client.get("/health", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in r.headers


def test_cors_allows_only_listed_origin(monkeypatch):
    monkeypatch.setenv("LOGDOCTOR_CORS_ORIGINS", "https://me.github.io/")
    client = TestClient(create_app(load_settings()))
    ok = client.get("/health", headers={"Origin": "https://me.github.io"})
    assert ok.headers["access-control-allow-origin"] == "https://me.github.io"
    other = client.get("/health", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in other.headers
    preflight = client.options(
        "/api/analyze/text",
        headers={"Origin": "https://me.github.io", "Access-Control-Request-Method": "POST",
                 "Access-Control-Request-Headers": "content-type"},
    )
    assert preflight.status_code == 200


@pytest.mark.parametrize("value", ["*", "me.github.io", "https://a.com,*"])
def test_bad_cors_setting_rejected(monkeypatch, value):
    monkeypatch.setenv("LOGDOCTOR_CORS_ORIGINS", value)
    with pytest.raises(ValueError):
        load_settings()


def test_api_key_never_written_to_local_storage():
    import re

    js = (ROOT / "app/static/app.js").read_text()
    # localStorage may only hold the history and the non-secret AI preferences (model names)
    for match in re.finditer(r"localStorage\.setItem\(([A-Za-z_]+)", js):
        assert match.group(1) in ("HISTORY_KEY", "PREF_KEY"), match.group(1)
    assert "keyStore(" in js and "sessionStorage" in js
    prefs = js[js.index("function writePrefs"): js.index("function remembered")]
    assert "api_key" not in prefs and "key" not in prefs.replace("PREF_KEY", "")


def test_page_explains_ai_options():
    html = (ROOT / "app/static/index.html").read_text()
    section = html[html.index("What this tool does"):]
    for word in ("Groq", "Gemini", "OpenRouter", "Mistral", "OpenAI", "Anthropic", "own key", "Load my models"):
        assert word in section, word
