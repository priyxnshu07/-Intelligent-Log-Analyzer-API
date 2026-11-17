import dataclasses

import pytest
from fastapi.testclient import TestClient

from app.config import load_settings
from app.limits import AnalysisGate
from app.main import create_app

LOG = (
    "2024-05-01 10:00:00 INFO started\n"
    "2024-05-01 10:00:01 ERROR db timeout after 30s\n"
    "2024-05-01 10:00:02 ERROR db timeout after 45s\n"
)


def make_client(**overrides):
    settings = dataclasses.replace(load_settings(), **overrides)
    return TestClient(create_app(settings))


@pytest.fixture
def client():
    return make_client(max_upload_bytes=2000, max_paste_bytes=500, max_lines=100)


def error_of(response):
    body = response.json()
    assert set(body) == {"error"}
    return body["error"]["code"], body["error"]["message"]


def test_limits_endpoint(client):
    body = client.get("/api/limits").json()
    assert body["max_upload_bytes"] == 2000
    assert body["max_paste_bytes"] == 500
    assert ".log" in body["allowed_extensions"]


def test_analyze_text_groups_errors(client):
    r = client.post("/api/analyze/text", json={"text": LOG})
    assert r.status_code == 200
    body = r.json()
    assert body["source"]["type"] == "paste"
    assert body["source"]["bytes"] == len(LOG.encode())
    assert len(body["analysis"]["groups"]) == 1
    assert body["analysis"]["groups"][0]["count"] == 2
    assert r.headers["cache-control"] == "no-store"


def test_analyze_file_raw_body(client):
    r = client.post("/api/analyze/file?filename=app.log", content=LOG.encode())
    assert r.status_code == 200
    body = r.json()
    assert body["source"]["type"] == "file"
    assert body["source"]["filename"] == "app.log"
    assert body["analysis"]["groups"][0]["count"] == 2


def test_file_content_type_is_ignored(client):
    r = client.post(
        "/api/analyze/file?filename=a.txt",
        content=LOG.encode(),
        headers={"content-type": "application/json"},
    )
    assert r.status_code == 200


def test_filename_is_cleaned(client):
    r = client.post("/api/analyze/file?filename=..%2F..%2Fetc%2Fapp.log", content=LOG.encode())
    assert r.json()["source"]["filename"] == "app.log"


def test_file_without_name_is_fine(client):
    r = client.post("/api/analyze/file", content=LOG.encode())
    assert r.status_code == 200
    assert r.json()["source"]["filename"] is None


def test_rotated_log_name_allowed(client):
    assert client.post("/api/analyze/file?filename=app.log.1", content=LOG.encode()).status_code == 200


@pytest.mark.parametrize("name", ["tool.exe", "photo.png", "notes.docx", "a.log.exe"])
def test_unsupported_extension(client, name):
    r = client.post(f"/api/analyze/file?filename={name}", content=LOG.encode())
    assert r.status_code == 415
    assert error_of(r)[0] == "unsupported_file_type"


def test_paste_too_large(client):
    r = client.post("/api/analyze/text", json={"text": "x" * 501})
    assert r.status_code == 413
    code, message = error_of(r)
    assert code == "payload_too_large"
    assert "file" in message  # points the user to the upload route


def test_paste_at_limit_ok(client):
    assert client.post("/api/analyze/text", json={"text": "e" * 500}).status_code == 200


def test_paste_body_far_too_large_rejected_early(client):
    r = client.post("/api/analyze/text", content=b"{" + b" " * 10_000)
    assert r.status_code == 413


def test_file_too_large_by_content_length(client):
    r = client.post("/api/analyze/file?filename=a.log", content=b"x" * 2001)
    assert r.status_code == 413


def test_file_too_large_when_chunked(client):
    def chunks():
        for _ in range(5):
            yield b"x" * 500

    # A generator body is sent chunked, with no Content-Length to check up front.
    r = client.post("/api/analyze/file?filename=a.log", content=chunks())
    assert r.status_code == 413
    assert error_of(r)[0] == "payload_too_large"


def test_empty_file(client):
    r = client.post("/api/analyze/file?filename=a.log", content=b"")
    assert r.status_code == 400
    assert error_of(r)[0] == "empty_input"


def test_blank_paste(client):
    r = client.post("/api/analyze/text", json={"text": "  \n \n"})
    assert error_of(r)[0] == "empty_input"


def test_invalid_json(client):
    r = client.post("/api/analyze/text", content=b"{not json")
    assert r.status_code == 400
    assert error_of(r)[0] == "invalid_json"


@pytest.mark.parametrize("payload", [{}, {"text": 5}, {"text": None}, [1, 2]])
def test_wrong_json_shape(client, payload):
    r = client.post("/api/analyze/text", json=payload)
    assert r.status_code == 422
    assert error_of(r)[0] == "invalid_request"


def test_filename_too_long_is_validation_error(client):
    r = client.post("/api/analyze/file?filename=" + "a" * 300, content=LOG.encode())
    assert r.status_code == 422
    assert error_of(r)[0] == "invalid_request"


def test_truncation_reported():
    client = make_client(max_upload_bytes=100_000, max_lines=100)
    text = "\n".join(f"2024-05-01 10:00:{i % 60:02d} ERROR failure {i}" for i in range(150))
    body = client.post("/api/analyze/file?filename=a.log", content=text.encode()).json()
    assert body["analysis"]["summary"]["truncated"] is True


def test_busy_server_returns_503(client):
    client.app.state.gate = AnalysisGate(0)
    r = client.post("/api/analyze/text", json={"text": LOG})
    assert r.status_code == 503
    assert r.headers["retry-after"] == "5"
    assert error_of(r)[0] == "server_busy"


def test_errors_use_one_format(client):
    r = client.get("/api/nope")
    assert r.status_code == 404
    assert error_of(r)[0] == "http_404"
    r = client.get("/api/analyze/text")
    assert r.status_code == 405
    assert error_of(r)[0] == "http_405"


def test_openapi_builds_with_bodies(client):
    spec = client.get("/openapi.json").json()
    assert "requestBody" in spec["paths"]["/api/analyze/text"]["post"]
    assert "requestBody" in spec["paths"]["/api/analyze/file"]["post"]
