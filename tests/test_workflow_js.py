import json
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).parent.parent
pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")


def run_js(expression):
    code = f"const W = require({json.dumps(str(ROOT / 'app/static/workflow.js'))}); console.log(JSON.stringify({expression}));"
    out = subprocess.run(["node", "-e", code], capture_output=True, text=True, check=True).stdout
    return json.loads(out)


def build(**options):
    return run_js(f"W.build({json.dumps(options)})")


@pytest.mark.parametrize("language,command", [
    ("python", "pytest"), ("node", "npm test"), ("java", "mvn test"), ("go", "go test"),
])
def test_generated_workflow_is_valid_yaml(language, command):
    doc = yaml.safe_load(build(language=language))
    steps = doc["jobs"]["check-logs"]["steps"]
    assert steps[0]["uses"].startswith("actions/checkout")
    runs = [s["run"] for s in steps if "run" in s]
    assert any(command in r and "tee app.log" in r for r in runs)
    last = steps[-1]
    assert last["uses"] == "priyxnshu07/universal-log-doctor@main" and last["with"]["log-path"] == "app.log"
    assert "fail-on" not in last["with"]
    # the run step must keep going so the log is analyzed even when tests fail
    assert [s for s in steps if "run" in s and "tee" in s["run"]][0]["continue-on-error"] is True


def test_fail_on_and_other_command():
    doc = yaml.safe_load(build(language="other", command="python main.py", failOn="error"))
    steps = doc["jobs"]["check-logs"]["steps"]
    assert steps[-1]["with"]["fail-on"] == "error"
    assert [s["run"] for s in steps if "run" in s] == ["python main.py 2>&1 | tee app.log"]


def test_other_command_is_one_line_and_cannot_break_out():
    text = build(language="other", command="echo hi\nuses: evil/action@v1")
    doc = yaml.safe_load(text)
    assert [s.get("uses") for s in doc["jobs"]["check-logs"]["steps"]].count("evil/action@v1") == 0
    assert len(doc["jobs"]["check-logs"]["steps"]) == 3  # checkout, run, log doctor


def test_bad_failon_ignored():
    assert "fail-on" not in build(language="python", failOn="rm -rf /")


@pytest.mark.parametrize("repo,ok", [("me/app", True), ("my-org/my.repo_1", True), ("noslash", False),
                                      ("a/b/c", False), ("a/b c", False), ("", False), ("../x", False), ("a/b?x=1", False)])
def test_repo_validation(repo, ok):
    assert run_js(f"W.validRepo({json.dumps(repo)})") is ok


@pytest.mark.parametrize("branch,ok", [("main", True), ("feature/x-1", True), ("a..b", False), ("a b", False), ("", False)])
def test_branch_validation(branch, ok):
    assert run_js(f"W.validBranch({json.dumps(branch)})") is ok


def test_new_file_url_roundtrips():
    text = build(language="python")
    url = run_js(f"W.newFileUrl('me/app','main',{json.dumps(text)})")
    assert url.startswith("https://github.com/me/app/new/main?filename=")
    from urllib.parse import parse_qs, urlparse
    q = parse_qs(urlparse(url).query)
    assert q["filename"] == [".github/workflows/log-doctor.yml"] and q["value"] == [text]
    assert len(url) < 6000
