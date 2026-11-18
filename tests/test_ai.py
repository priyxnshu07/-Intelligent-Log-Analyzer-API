import dataclasses
import logging

import pytest
from fastapi.testclient import TestClient

from app import ai
from app.config import load_settings
from app.main import create_app
from logdoctor import analyze

KEY = "sk-test-SECRETSECRET1234567890"
LOG = (
    "2024-05-01 10:00:00 INFO started\n"
    "2024-05-01 10:00:01 ERROR db timeout after 30s\n"
    "2024-05-01 10:00:02 ERROR db timeout after 45s\n"
)


class FakeTransport:
    def __init__(self, status=200, data=None, error=None):
        self.status, self.data, self.error, self.calls = status, data, error, []

    def __call__(self, url, headers, payload, timeout):
        self.calls.append((url, headers, payload, timeout))
        if self.error:
            raise self.error
        return self.status, self.data


def ok_openai(text="Check the database connection pool."):
    return {"choices": [{"message": {"content": text}}]}


def make(transport):
    app = create_app(dataclasses.replace(load_settings()))
    app.state.ai_transport = transport
    return TestClient(app)


def analysis_json(client, log=LOG):
    return client.post("/api/analyze/text", json={"text": log}).json()


def body(client, **extra):
    data = {"provider": "groq", "api_key": KEY, "analysis": analysis_json(client)}
    data.update(extra)
    return data


def test_success_openai_style():
    t = FakeTransport(data=ok_openai())
    c = make(t)
    r = c.post("/api/ai/diagnose", json=body(c))
    assert r.status_code == 200
    j = r.json()
    assert j["text"] == "Check the database connection pool."
    assert j["provider"] == "groq" and j["model"] == "openai/gpt-oss-20b"
    assert j["groups_sent"] == 1
    url, headers, payload, _ = t.calls[0]
    assert url == "https://api.groq.com/openai/v1/chat/completions"
    assert headers["Authorization"] == f"Bearer {KEY}"
    assert payload["max_tokens"] == ai.MAX_OUTPUT_TOKENS


def test_openai_uses_max_completion_tokens():
    t = FakeTransport(data=ok_openai())
    c = make(t)
    c.post("/api/ai/diagnose", json=body(c, provider="openai"))
    assert "max_completion_tokens" in t.calls[0][2]
    assert t.calls[0][0].startswith("https://api.openai.com/")


def test_anthropic_shape():
    t = FakeTransport(data={"content": [{"type": "text", "text": "Answer"}]})
    c = make(t)
    r = c.post("/api/ai/diagnose", json=body(c, provider="anthropic", model="my-model"))
    assert r.json()["text"] == "Answer" and r.json()["model"] == "my-model"
    url, headers, payload, _ = t.calls[0]
    assert url == "https://api.anthropic.com/v1/messages"
    assert headers["x-api-key"] == KEY and "anthropic-version" in headers
    assert payload["system"] and payload["messages"][0]["role"] == "user"


def test_prompt_is_an_excerpt_not_the_whole_log():
    big = "".join(f"2024-05-01 10:00:{i % 60:02d} ERROR failure kind{i} happened here\n" for i in range(300))
    t = FakeTransport(data=ok_openai())
    c = make(t)
    c.post("/api/ai/diagnose", json=body(c, analysis=analysis_json(c, big)))
    user = t.calls[0][2]["messages"][-1]["content"]
    assert len(user) <= ai.PROMPT_CHARS
    assert user.count("### Problem") <= ai.EXCERPT_GROUPS
    assert "untrusted" in t.calls[0][2]["messages"][0]["content"]


def test_unknown_provider_rejected():
    c = make(FakeTransport())
    r = c.post("/api/ai/diagnose", json=body(c, provider="evil"))
    assert r.status_code == 422


@pytest.mark.parametrize("key", ["short", "has space in it 12345", "line\nbreak12345", "x" * 400])
def test_bad_keys_rejected_and_not_echoed(key):
    t = FakeTransport(data=ok_openai())
    c = make(t)
    r = c.post("/api/ai/diagnose", json=body(c, api_key=key))
    assert r.status_code == 422 and not t.calls
    assert key.strip() not in r.text or len(key.strip()) < 8


@pytest.mark.parametrize("model", ["bad model", "a;b", "../x", "x" * 100])
def test_bad_model_rejected(model):
    c = make(FakeTransport(data=ok_openai()))
    r = c.post("/api/ai/diagnose", json=body(c, model=model))
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_model"


def test_no_groups_is_refused():
    t = FakeTransport(data=ok_openai())
    c = make(t)
    r = c.post("/api/ai/diagnose", json=body(c, analysis=analysis_json(c, "2024-05-01 10:00:00 INFO ok\n")))
    assert r.status_code == 400 and not t.calls


@pytest.mark.parametrize(
    "status,code,http",
    [(401, "ai_key_rejected", 401), (403, "ai_forbidden", 403), (429, "ai_rate_limited", 429),
     (400, "ai_request_rejected", 400), (404, "ai_request_rejected", 400),
     (500, "ai_provider_error", 502), (503, "ai_provider_error", 502)],
)
def test_provider_errors_mapped_and_never_echoed(status, code, http):
    t = FakeTransport(status=status, data={"error": {"message": f"Incorrect API key provided: {KEY[:12]}..."}})
    c = make(t)
    r = c.post("/api/ai/diagnose", json=body(c))
    assert r.status_code == http and r.json()["error"]["code"] == code
    assert KEY[:12] not in r.text


def test_unreachable_and_garbage():
    c = make(FakeTransport(error=ai.TransportError()))
    assert c.post("/api/ai/diagnose", json=body(c)).json()["error"]["code"] == "ai_unreachable"
    c = make(FakeTransport(status=200, data=None))
    assert c.post("/api/ai/diagnose", json=body(c)).status_code == 502
    c = make(FakeTransport(status=200, data={"choices": []}))
    assert c.post("/api/ai/diagnose", json=body(c)).json()["error"]["code"] == "ai_empty_answer"


def test_unexpected_exception_does_not_leak_key():
    c = make(FakeTransport(error=RuntimeError(f"boom {KEY}")))
    r = c.post("/api/ai/diagnose", json=body(c))
    assert r.status_code == 502 and KEY not in r.text


def test_answer_is_capped_and_control_chars_removed():
    c = make(FakeTransport(data=ok_openai("a\x00b" + "z" * 20000)))
    text = c.post("/api/ai/diagnose", json=body(c)).json()["text"]
    assert len(text) <= ai.MAX_ANSWER_CHARS and "\x00" not in text


def test_key_never_logged(caplog):
    caplog.set_level(logging.DEBUG)
    t = FakeTransport(status=401, data={"error": {"message": f"bad key {KEY}"}})
    c = make(t)
    c.post("/api/ai/diagnose", json=body(c))
    c.post("/api/ai/diagnose", json=body(c, api_key="short"))
    assert KEY not in caplog.text
    assert KEY[:12] not in caplog.text


def test_key_hidden_in_repr():
    from app.schemas import AiRequest

    req = AiRequest.model_validate(
        {"provider": "groq", "api_key": KEY, "analysis": analysis_json(make(FakeTransport()))}
    )
    assert KEY not in repr(req) and KEY not in str(req)


def test_ai_is_optional_other_endpoints_work_without_it():
    c = make(FakeTransport())
    assert c.post("/api/analyze/text", json={"text": LOG}).status_code == 200
    assert c.post("/api/report", json=analysis_json(c)).status_code == 200


def test_urllib_transport_refuses_plain_http():
    with pytest.raises(ai.TransportError):
        ai.urllib_transport("http://example.com/x", {}, {}, 1.0)


def test_urllib_transport_does_not_follow_redirects():
    import http.server
    import threading

    class H(http.server.BaseHTTPRequestHandler):
        seen = []

        def do_POST(self):
            H.seen.append(self.path)
            if self.path == "/start":
                self.send_response(307)
                self.send_header("Location", "/other")
                self.end_headers()
            else:
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"{}")

        def log_message(self, *a):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        status, data = ai.urllib_transport(
            f"http://127.0.0.1:{server.server_port}/start", {"Content-Type": "application/json"}, {}, 5.0,
            allow_http=True,
        )
    finally:
        server.shutdown()
    assert status == 307 and H.seen == ["/start"]


def test_excerpt_strips_control_chars():
    a = analyze("2024-05-01 10:00:00 ERROR bad\x00thing\x1b[31m happened\n")
    assert "\x00" not in ai.build_excerpt(a) and "\x1b" not in ai.build_excerpt(a)


def test_urllib_transport_sends_a_real_user_agent():
    import http.server
    import threading

    seen = {}

    class H(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            seen["ua"] = self.headers.get("User-Agent")
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"{}")

        def log_message(self, *a):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        ai.urllib_transport(f"http://127.0.0.1:{server.server_port}/", {}, {}, 5.0, allow_http=True)
    finally:
        server.shutdown()
    assert seen["ua"].startswith("universal-log-doctor/") and "urllib" not in seen["ua"].lower()
