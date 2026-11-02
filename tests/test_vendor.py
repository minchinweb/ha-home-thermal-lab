"""The panel's vendored scripts match their pins (``invoke vendor`` fetches them)."""

import hashlib
import json
from pathlib import Path

FRONTEND = Path("custom_components/home_thermal_lab/frontend")


def test_vendored_files_match_their_pins():
    pins = json.loads((FRONTEND / "vendor.json").read_text(encoding="utf-8"))
    assert pins
    for name, pin in pins.items():
        body = (FRONTEND / name).read_bytes()
        assert hashlib.sha256(body).hexdigest() == pin["sha256"], name
        assert pin["version"] in pin["url"]


def test_the_page_loads_the_pinned_version():
    pins = json.loads((FRONTEND / "vendor.json").read_text(encoding="utf-8"))
    page = (FRONTEND / "index.html").read_text(encoding="utf-8")
    version = pins["chart.umd.min.js"]["version"]
    assert f'src="chart.umd.min.js?v={version}"' in page
    assert "https://" not in page.split("<script", 1)[1].split(">", 1)[0]
