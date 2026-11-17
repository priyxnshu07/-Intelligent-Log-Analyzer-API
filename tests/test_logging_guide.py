import pytest

from logdoctor import analyze

SAMPLES = {
    "python": "2024-05-01 10:00:01,123 ERROR app: db timeout\n",
    "java": "2024-05-01 10:00:01.123 ERROR [main] com.app.Db - db timeout\n",
    "node": '{"level":50,"time":1714557601123,"msg":"db timeout"}\n',
    "go": 'time=2024-05-01T10:00:01.123Z level=ERROR msg="db timeout"\n',
    "cpp": "2024-05-01 10:00:01.123 [error] db timeout\n",
}


@pytest.mark.parametrize("language", SAMPLES)
def test_documented_formats_are_read(language):
    result = analyze(SAMPLES[language])
    assert [g.level for g in result.groups] == ["ERROR"]
    assert "db timeout" in result.groups[0].title
    assert result.summary.first_timestamp is not None
