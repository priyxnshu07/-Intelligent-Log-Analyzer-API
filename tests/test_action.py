import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
SCRIPT = ROOT / "scripts/action_run.sh"
LOG = "2024-05-01 10:00:01 ERROR db timeout after 30s\n2024-05-01 10:00:02 WARNING slow query\n"


def run(tmp_path, log=LOG, **env):
    path = tmp_path / "app.log"
    if log is not None:
        path.write_text(log)
    summary = tmp_path / "summary.md"
    full = {**os.environ, "PYTHONPATH": str(ROOT), "LOGDOCTOR_LOG_PATH": str(path),
            "LOGDOCTOR_REPORT": str(tmp_path / "r.md"), "GITHUB_STEP_SUMMARY": str(summary),
            "PATH": str(Path(sys.executable).parent) + os.pathsep + os.environ["PATH"]}
    full.update(env)
    p = subprocess.run(["bash", str(SCRIPT)], capture_output=True, text=True, env=full, cwd=tmp_path)
    return p, summary


def test_writes_summary_and_passes_without_fail_on(tmp_path):
    p, summary = run(tmp_path)
    assert p.returncode == 0
    text = summary.read_text()
    assert text.startswith("## Log Doctor") and "db timeout" in text
    assert (tmp_path / "r.md").exists()


@pytest.mark.parametrize("level,code", [("warning", 1), ("error", 1), ("critical", 0)])
def test_fail_on_threshold(tmp_path, level, code):
    p, summary = run(tmp_path, LOGDOCTOR_FAIL_ON=level)
    assert p.returncode == code
    assert "Log Doctor" in summary.read_text()  # summary is written even when failing


def test_missing_file_is_an_error(tmp_path):
    p, _ = run(tmp_path, log=None)
    assert p.returncode == 2 and "not found" in p.stderr


def test_bad_fail_on_value(tmp_path):
    p, _ = run(tmp_path, LOGDOCTOR_FAIL_ON="nope")
    assert p.returncode == 2


def test_hostile_path_is_not_executed(tmp_path):
    p, _ = run(tmp_path, LOGDOCTOR_LOG_PATH='x"; touch pwned; "')
    assert p.returncode == 2 and not (tmp_path / "pwned").exists()


def test_action_file_never_interpolates_inputs_into_shell():
    import yaml

    action = yaml.safe_load((ROOT / "action.yml").read_text())
    assert action["runs"]["using"] == "composite"
    for step in action["runs"]["steps"]:
        if "run" in step:
            assert "${{" not in step["run"], "pass inputs through env, not inside the script"
    assert {"log-path", "fail-on"} <= set(action["inputs"])
    assert action["inputs"]["log-path"]["required"] is True
