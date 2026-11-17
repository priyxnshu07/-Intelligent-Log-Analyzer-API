"""Copy the web page into a folder that any static host can serve.

    python scripts/build_site.py site https://your-api.onrender.com

The page then shows the sample report instantly and talks to the API at the
given address. The API must list the page's address in LOGDOCTOR_CORS_ORIGINS.
"""

import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "app/static"


def build_site(destination: Path, api_url: str) -> None:
    if not api_url.startswith(("http://", "https://")):
        raise ValueError("api_url must start with http:// or https://")
    if destination.exists():
        shutil.rmtree(destination)
    # Same layout the server uses: index.html at the root, assets under static/.
    shutil.copytree(STATIC, destination / "static")
    (destination / "static" / "index.html").rename(destination / "index.html")
    config = "window.LOGDOCTOR_API = " + json.dumps(api_url.rstrip("/")) + ";\n"
    (destination / "static" / "config.js").write_text(config, encoding="utf-8")
    (destination / ".nojekyll").write_text("", encoding="utf-8")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    build_site(Path(sys.argv[1]), sys.argv[2])
    print(f"built {sys.argv[1]}")
