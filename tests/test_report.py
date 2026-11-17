import dataclasses
import re

from fastapi.testclient import TestClient

from app.config import load_settings
from app.main import create_app
from logdoctor import analyze
from logdoctor.analyze import MAX_GROUPS
from logdoctor.report import MAX_DETAILED_GROUPS, render_markdown

LOG = (
    "2024-05-01 10:00:00 INFO started\n"
    "2024-05-01 10:00:01 ERROR Error: connect ECONNREFUSED 127.0.0.1:5432\n"
    "2024-05-01 10:00:02 ERROR Error: connect ECONNREFUSED 127.0.0.1:5433\n"
    "2024-05-01 10:00:03 WARNING slow disk\n"
)


def outside_code(markdown):
    """The report with fenced code blocks removed. Only this part is rendered as Markdown."""
    return re.sub(r"^(`{3,})text\n.*?^\1$", "", markdown, flags=re.DOTALL | re.MULTILINE)


def word(i):
    """A distinct short word for every number (digits would be masked when grouping)."""
    return "".join(chr(97 + (i // 26**k) % 26) for k in range(4))


def report(text=LOG, name=None):
    return render_markdown(analyze(text), name)


def test_report_has_the_expected_sections():
    out = report(name="app.log")
    for heading in ("# Log diagnosis report", "## Summary", "## Timeline", "## Problems", "## About this report"):
        assert heading in out
    assert "Source: app.log" in out
    assert "Seen **2** time(s)" in out
    assert "Probable causes" in out and "Nothing is listening" in out
    assert "not stored" in out


def test_report_is_deterministic():
    assert report() == report()


def test_clean_log_report():
    out = report("2024-05-01 10:00:00 INFO all good\n")
    assert "No warnings or errors were found." in out and "## Timeline" not in out


def test_html_and_links_in_log_text_cannot_become_markup():
    nasty = "2024-05-01 10:00:00 ERROR <script>alert(1)</script> [click me](javascript:alert(1)) ![x](http://evil/x.png) | a | b"
    out = outside_code(report(nasty, name="<img src=x onerror=alert(1)>.log"))
    assert re.search(r"(?<!\\)<", out) is None  # every < is escaped, so no HTML can start
    assert "\\<script\\>" in out
    assert re.search(r"(?<!\\)\[click me\]", out) is None  # the link bracket is escaped
    assert re.search(r"(?<!\\)\|", out) is None  # no unescaped table breaks


def test_sample_with_backticks_cannot_close_the_code_fence():
    text = "2024-05-01 10:00:00 ERROR boom ```` and ``` then\n# Heading injected\n"
    out = report(text)
    fence = re.search(r"^(`{3,})text$", out, re.MULTILINE).group(1)
    assert len(fence) >= 5  # longer than the 4-backtick run in the log
    body = out.split(fence + "text", 1)[1].split("\n" + fence, 1)[0]
    assert fence not in body
    assert out.count("\n" + fence) >= 1


def test_control_characters_and_newlines_are_removed_from_headings():
    out = report("2024-05-01 10:00:00 ERROR bad\x00thing\x1b[31m red\n")
    heading = next(line for line in out.splitlines() if line.startswith("### 1."))
    assert "\x00" not in out and "\x1b" not in out
    assert "\n" not in heading


def test_long_samples_are_shortened():
    out = report("2024-05-01 10:00:00 ERROR " + "x" * 9000)
    assert "[shortened]" in out or len(out) < 9000


def test_only_the_first_groups_are_detailed():
    lines = [f"2024-05-01 10:00:00 ERROR distinct failure {word(i)}" for i in range(MAX_DETAILED_GROUPS + 7)]
    out = report("\n".join(lines))
    assert f"### {MAX_DETAILED_GROUPS}." in out and f"### {MAX_DETAILED_GROUPS + 1}." not in out
    assert "...and 7 more group(s)" in out


def test_groups_omitted_by_the_analysis_are_mentioned():
    lines = [f"2024-05-01 10:00:00 ERROR failure {word(i)}" for i in range(MAX_GROUPS + 30)]
    result = analyze("\n".join(lines))
    assert len(result.groups) == MAX_GROUPS
    assert result.summary.group_count == MAX_GROUPS + 30 and result.summary.groups_omitted == 30
    assert "30 further group(s)" in render_markdown(result)


# ---- API ----

def client():
    return TestClient(create_app(dataclasses.replace(load_settings(), max_upload_bytes=200_000)))


def analyzed(c, text=LOG, name="app.log"):
    return c.post(f"/api/analyze/file?filename={name}", content=text.encode()).json()


def test_report_endpoint_returns_markdown_download():
    c = client()
    r = c.post("/api/report", json=analyzed(c))
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/markdown")
    assert 'attachment; filename="log-report.md"' in r.headers["content-disposition"]
    assert r.headers["cache-control"] == "no-store"
    assert "Source: app.log" in r.text and "Probable causes" in r.text


def test_report_endpoint_matches_the_library():
    c = client()
    data = analyzed(c)
    assert c.post("/api/report", json=data).text == render_markdown(analyze(LOG), "app.log")


def test_report_endpoint_rejects_bad_bodies():
    c = client()
    assert c.post("/api/report", content=b"{nope").status_code == 400
    r = c.post("/api/report", json={"analysis": "no"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_request"
    r = c.post("/api/report", json=[1, 2])
    assert r.status_code == 422


def test_report_endpoint_size_limit():
    c = client()
    assert c.post("/api/report", content=b"x" * 200_001).status_code == 413


def test_forged_analysis_still_cannot_inject_markup():
    c = client()
    data = analyzed(c)
    data["analysis"]["groups"][0]["title"] = "<script>alert(1)</script>"
    data["analysis"]["groups"][0]["causes"][0]["cause"] = "[x](javascript:alert(1))"
    data["source"]["filename"] = "<b>x</b>"
    out = outside_code(c.post("/api/report", json=data).text)
    assert re.search(r"(?<!\\)<", out) is None
    assert re.search(r"(?<!\\)\[x\]", out) is None


def test_openapi_lists_report_body():
    spec = client().get("/openapi.json").json()
    assert "requestBody" in spec["paths"]["/api/report"]["post"]


def test_page_has_download_buttons():
    page = client().get("/").text
    assert 'id="dl-report"' in page and 'id="dl-json"' in page
