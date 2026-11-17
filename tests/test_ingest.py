import codecs

import pytest

from app.errors import ApiError
from app.ingest import check_extension, clean_filename, decode_log


def test_decode_plain_utf8():
    result = decode_log("héllo\n".encode())
    assert result.text == "héllo\n"
    assert result.encoding == "utf-8"
    assert result.warnings == []


def test_decode_utf8_bom_is_removed():
    result = decode_log(codecs.BOM_UTF8 + b"ERROR x")
    assert result.text == "ERROR x"


def test_decode_utf16():
    result = decode_log("ERROR boom\n".encode("utf-16"))
    assert result.text == "ERROR boom\n"
    assert result.encoding == "utf-16"


def test_invalid_bytes_replaced_with_warning():
    result = decode_log(b"ERROR caf\xe9 failed")
    assert "\ufffd" in result.text
    assert len(result.warnings) == 1


@pytest.mark.parametrize(
    "data,code",
    [
        (b"PK\x03\x04rest", "unsupported_file_type"),
        (b"\x1f\x8bdata", "unsupported_file_type"),
        (b"%PDF-1.7", "unsupported_file_type"),
        (b"\x89PNG\r\n", "unsupported_file_type"),
        (b"abc\x00def", "binary_file"),
    ],
)
def test_binary_rejected(data, code):
    with pytest.raises(ApiError) as caught:
        decode_log(data)
    assert caught.value.status_code == 415
    assert caught.value.code == code


@pytest.mark.parametrize(
    "raw,expected",
    [
        (None, None),
        ("", None),
        ("app.log", "app.log"),
        ("C:\\logs\\app.log", "app.log"),
        ("../../etc/passwd", "passwd"),
        ("a\x00b\nc.log", "abc.log"),
        ("folder/", None),
    ],
)
def test_clean_filename(raw, expected):
    assert clean_filename(raw) == expected


@pytest.mark.parametrize("name", [None, "app", "app.log", "APP.LOG", "a.json", "a.csv", "a.jsonl", "app.log.12"])
def test_extension_allowed(name):
    check_extension(name)


@pytest.mark.parametrize("name", ["a.exe", "a.zip", "a.pdf", "a.log.zip"])
def test_extension_rejected(name):
    with pytest.raises(ApiError) as caught:
        check_extension(name)
    assert caught.value.status_code == 415
