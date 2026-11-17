import dataclasses
import io
import zipfile

import pytest
from fastapi.testclient import TestClient

from app.config import load_settings
from app.main import create_app
from app.ratelimit import MAX_TRACKED_VISITORS, RateLimiter
from app import ziputil

LOG = "2024-05-01 10:00:01 ERROR db timeout after 30s\n"


def make(**o):
    return TestClient(create_app(dataclasses.replace(load_settings(), **o)))


def make_zip(files, method=zipfile.ZIP_DEFLATED):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", method) as z:
        for name, data in files.items():
            z.writestr(name, data)
    return buf.getvalue()


def post_zip(c, data, name="logs.zip"):
    return c.post(f"/api/analyze/file?filename={name}", content=data)


# ---------------- rate limiter

def test_limiter_blocks_then_recovers():
    t = [0.0]
    r = RateLimiter(3, clock=lambda: t[0])
    assert [r.check("a") for _ in range(3)] == [None] * 3
    wait = r.check("a")
    assert wait is not None and 1 <= wait <= 60
    assert r.check("b") is None  # another visitor is not affected
    t[0] = 61
    assert r.check("a") is None


def test_limiter_memory_is_bounded():
    r = RateLimiter(1)
    for i in range(MAX_TRACKED_VISITORS + 500):
        r.check(f"ip{i}")
    assert len(r._seen) <= MAX_TRACKED_VISITORS


def test_analyze_rate_limited_with_retry_after():
    c = make(rate_limit_analyses_per_min=2)
    for _ in range(2):
        assert c.post("/api/analyze/text", json={"text": LOG}).status_code == 200
    r = c.post("/api/analyze/text", json={"text": LOG})
    assert r.status_code == 429
    assert r.json()["error"]["code"] == "rate_limited" and int(r.headers["Retry-After"]) >= 1


def test_ai_limit_is_separate():
    c = make(rate_limit_analyses_per_min=50, rate_limit_ai_per_min=1)
    for _ in range(3):
        c.post("/api/ai/diagnose", json={})
    r = c.post("/api/ai/diagnose", json={})
    assert r.status_code == 429
    assert c.post("/api/analyze/text", json={"text": LOG}).status_code == 200


def test_health_and_limits_not_limited():
    c = make(rate_limit_analyses_per_min=1)
    for _ in range(5):
        assert c.get("/health").status_code == 200
        assert c.get("/api/limits").status_code == 200


def test_forwarded_for_only_trusted_when_enabled():
    c = make(rate_limit_analyses_per_min=1, trust_proxy=False)
    c.post("/api/analyze/text", json={"text": LOG}, headers={"X-Forwarded-For": "1.1.1.1"})
    assert c.post("/api/analyze/text", json={"text": LOG}, headers={"X-Forwarded-For": "2.2.2.2"}).status_code == 429
    c = make(rate_limit_analyses_per_min=1, trust_proxy=True)
    h1, h2 = {"X-Forwarded-For": "spoof, 1.1.1.1"}, {"X-Forwarded-For": "spoof, 2.2.2.2"}
    assert c.post("/api/analyze/text", json={"text": LOG}, headers=h1).status_code == 200
    assert c.post("/api/analyze/text", json={"text": LOG}, headers=h2).status_code == 200
    assert c.post("/api/analyze/text", json={"text": LOG}, headers=h1).status_code == 429
    h3 = {"X-Forwarded-For": "other-spoof, 1.1.1.1"}  # changing the visitor-written part does not help
    assert c.post("/api/analyze/text", json={"text": LOG}, headers=h3).status_code == 429


# ---------------- zip

def test_zip_reads_logs_in_name_order():
    z = make_zip({"b.log": "2024-05-01 10:00:02 ERROR second failure\n", "a.log": "2024-05-01 10:00:01 ERROR first failure\n", "notes.exe": "x", "img/p.png": "x"})
    r = post_zip(make(), z)
    assert r.status_code == 200
    j = r.json()
    assert j["source"]["type"] == "zip"
    assert j["analysis"]["summary"]["group_count"] == 2
    assert j["analysis"]["groups"][0]["title"] == "first failure"
    assert "Read 2 file(s)" in j["source"]["warnings"][0] and "a.log, b.log" in j["source"]["warnings"][0]
    assert any("skipped" in w for w in j["source"]["warnings"])


def test_zip_detected_by_content_even_without_zip_name():
    z = make_zip({"a.log": LOG})
    assert post_zip(make(), z, "upload.txt").json()["source"]["type"] == "zip"


def test_zip_name_but_not_a_zip():
    r = post_zip(make(), b"just text", "x.zip")
    assert r.status_code == 400 and r.json()["error"]["code"] == "invalid_zip"


def test_corrupt_zip():
    data = bytearray(make_zip({"a.log": LOG * 50}))
    r = post_zip(make(), bytes(data[: len(data) // 2]))
    assert r.status_code == 400 and r.json()["error"]["code"] == "invalid_zip"


def test_zip_without_logs():
    r = post_zip(make(), make_zip({"doc.xml": "<a/>", "p.png": "x"}))
    assert r.status_code == 415 and r.json()["error"]["code"] == "zip_no_logs"


@pytest.mark.parametrize("name", ["../evil.log", "/abs/evil.log", "a/../../evil.log", "..\\evil.log", "dir\\x.log", ".hidden.log", "__MACOSX/a.log"])
def test_unsafe_member_names_skipped(name):
    z = make_zip({name: LOG, "ok.log": LOG})
    j = post_zip(make(), z).json()
    assert "Read 1 file(s)" in j["source"]["warnings"][0]


def test_zip_bomb_stopped_by_real_size(monkeypatch):
    monkeypatch.setattr(ziputil, "MAX_MEMBER_BYTES", 100_000)
    z = make_zip({"big.log": "A" * 5_000_000})  # compresses to a few KB
    assert len(z) < 20_000
    r = post_zip(make(), z)
    assert r.status_code == 413 and r.json()["error"]["code"] == "zip_too_large"


def test_zip_total_size_limit(monkeypatch):
    monkeypatch.setattr(ziputil, "MAX_TOTAL_BYTES", 150_000)
    monkeypatch.setattr(ziputil, "MAX_MEMBER_BYTES", 100_000)
    z = make_zip({"a.log": "B" * 90_000, "b.log": "C" * 90_000})
    assert post_zip(make(), z).json()["error"]["code"] == "zip_too_large"


def test_lying_header_does_not_bypass_limit(monkeypatch):
    monkeypatch.setattr(ziputil, "MAX_MEMBER_BYTES", 50_000)
    data = bytearray(make_zip({"a.log": "D" * 400_000}))
    # make the central directory claim the file is tiny
    idx = data.rfind(b"PK\x01\x02")
    data[idx + 24: idx + 28] = (10).to_bytes(4, "little")
    r = post_zip(make(), bytes(data))
    assert r.status_code in (400, 413)  # refused either way, never fully unpacked


def test_too_many_entries(monkeypatch):
    monkeypatch.setattr(ziputil, "MAX_ENTRIES_SCANNED", 5)
    z = make_zip({f"f{i}.log": LOG for i in range(10)})
    assert post_zip(make(), z).json()["error"]["code"] == "zip_too_many_files"


def test_only_first_files_read(monkeypatch):
    monkeypatch.setattr(ziputil, "MAX_FILES_READ", 3)
    z = make_zip({f"f{i:02}.log": LOG for i in range(6)})
    w = post_zip(make(), z).json()["source"]["warnings"]
    assert "Read 3 file(s)" in w[0] and any("first 3" in x for x in w)


def test_encrypted_zip_refused():
    data = bytearray(make_zip({"a.log": LOG}))
    for sig, off in ((b"PK\x03\x04", 6), (b"PK\x01\x02", 8)):
        i = data.find(sig)
        data[i + off] |= 1
    r = post_zip(make(), bytes(data))
    assert r.status_code == 415 and r.json()["error"]["code"] == "zip_encrypted"


def test_nested_zip_is_not_opened():
    inner = make_zip({"deep.log": LOG})
    r = post_zip(make(), make_zip({"inner.zip": inner}))
    assert r.json()["error"]["code"] == "zip_no_logs"


def test_zip_upload_size_still_limited():
    r = post_zip(make(max_upload_bytes=1000), make_zip({"a.log": "x" * 5000}) + b"0" * 2000)
    assert r.status_code == 413


# ---------------- headers

def test_security_headers_on_page_and_api():
    c = make()
    for path in ("/", "/health", "/api/limits"):
        h = c.get(path).headers
        assert h["x-content-type-options"] == "nosniff"
        assert h["x-frame-options"] == "DENY" and h["referrer-policy"] == "no-referrer"
    csp = c.get("/").headers["content-security-policy"]
    assert "default-src 'self'" in csp and "unsafe-inline" not in csp and "unsafe-eval" not in csp
    assert "content-security-policy" not in c.get("/docs").headers
