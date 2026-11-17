import io
import json
import sys

from logdoctor.cli import main

LOG = (
    "2024-05-01 10:00:00 INFO started\n"
    "2024-05-01 10:00:01 ERROR db timeout after 30s\n"
    "2024-05-01 10:00:02 ERROR db timeout after 45s\n"
    "2024-05-01 10:00:03 WARNING slow disk\n"
)


def write(tmp_path, text=LOG, name="app.txt"):
    path = tmp_path / name
    path.write_text(text)
    return str(path)


def test_text_report(tmp_path, capsys):
    assert main([write(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "db timeout" in out and "(x2)" in out and "line(s): 2, 3" in out


def test_json_output(tmp_path, capsys):
    assert main([write(tmp_path), "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["groups"][0]["count"] == 2


def test_reads_stdin(monkeypatch, capsys):
    class FakeStdin:
        buffer = io.BytesIO(LOG.encode())

    monkeypatch.setattr(sys, "stdin", FakeStdin())
    assert main([]) == 0
    assert "db timeout" in capsys.readouterr().out


def test_clean_log(tmp_path, capsys):
    assert main([write(tmp_path, "2024-05-01 10:00:00 INFO ok\n")]) == 0
    assert "No warnings or errors found" in capsys.readouterr().out


def test_missing_file(capsys):
    assert main(["/no/such/file.log"]) == 2
    assert "cannot read" in capsys.readouterr().err


def test_fail_on(tmp_path):
    path = write(tmp_path)
    assert main([path, "--fail-on", "error"]) == 1
    assert main([path, "--fail-on", "critical"]) == 0
    assert main([path, "--fail-on", "warning"]) == 1
    clean = write(tmp_path, "2024-05-01 10:00:00 INFO ok\n", "clean.txt")
    assert main([clean, "--fail-on", "warning"]) == 0


def test_bad_numbers(tmp_path, capsys):
    assert main([write(tmp_path), "--top", "0"]) == 2


def test_top_limits_output(tmp_path, capsys):
    text = "".join(f"2024-05-01 10:00:0{i} ERROR distinct problem {chr(97 + i)}x\n" for i in range(5))
    main([write(tmp_path, text), "--top", "2"])
    assert "more (use --top" in capsys.readouterr().out


def test_binary_garbage_does_not_crash(tmp_path):
    path = tmp_path / "bin.dat"
    path.write_bytes(bytes(range(256)) * 20)
    assert main([str(path)]) == 0
