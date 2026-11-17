"""Regenerate app/static/sample-report.json from the sample log.

Run after changing the engine or the sample:  python scripts/make_sample_report.py
A test fails if the committed file is out of date.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from logdoctor import analyze  # noqa: E402

SAMPLE = ROOT / "app/static/samples/python-web-app.txt"
OUTPUT = ROOT / "app/static/sample-report.json"


def build() -> str:
    text = SAMPLE.read_text(encoding="utf-8")
    report = {
        "source": {"type": "sample", "filename": SAMPLE.name, "bytes": len(text.encode()),
                   "encoding": "utf-8", "warnings": []},
        "analysis": analyze(text).to_dict(),
    }
    return json.dumps(report, indent=1) + "\n"


if __name__ == "__main__":
    OUTPUT.write_text(build(), encoding="utf-8")
    print(f"wrote {OUTPUT.relative_to(ROOT)}")
