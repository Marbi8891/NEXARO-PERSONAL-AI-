"""El frontend debe cumplir la CSP estricta: nada en línea y nada de HTML construido con datos."""

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from nexaro_api.main import create_app
from nexaro_core.config import Settings

FRONTEND = Path(__file__).resolve().parents[2] / "frontend"
JS_FILES = sorted(FRONTEND.rglob("*.js"))
FORBIDDEN_JS = [
    r"\.innerHTML",
    r"\.outerHTML",
    r"insertAdjacentHTML",
    r"document\.write",
    r"\beval\(",
    r"new Function",
    r"setTimeout\(\s*[\"']",
]


def test_frontend_files_exist() -> None:
    assert (FRONTEND / "index.html").is_file()
    assert any(p.name == "main.js" for p in JS_FILES)


def test_index_has_no_inline_script_style_or_handlers() -> None:
    html = (FRONTEND / "index.html").read_text(encoding="utf-8")
    assert not re.search(r"<script(?![^>]*\bsrc=)", html)
    assert "<style" not in html
    assert not re.search(r"\sstyle\s*=", html)
    assert not re.search(r"\son[a-z]+\s*=", html)


@pytest.mark.parametrize("pattern", FORBIDDEN_JS)
def test_js_avoids_dangerous_apis(pattern: str) -> None:
    offenders = [p.name for p in JS_FILES if re.search(pattern, p.read_text(encoding="utf-8"))]
    assert offenders == []


def test_js_does_not_use_inline_styles() -> None:
    # style.cssText o setAttribute("style") romperían style-src 'self'.
    offenders = [
        p.name
        for p in JS_FILES
        if re.search(
            r"""setAttribute\(\s*["']style|\.cssText|["']style["']\s*:""",
            p.read_text(encoding="utf-8"),
        )
    ]
    assert offenders == []


def test_csp_and_manifest_are_served(tmp_path: Path) -> None:
    settings = Settings(database_path=tmp_path / "n.db", frontend_path=FRONTEND)
    with TestClient(create_app(settings)) as client:
        index = client.get("/")
        csp = index.headers["content-security-policy"]
        assert "script-src 'self'" in csp
        assert "'unsafe-inline'" not in csp
        assert "frame-ancestors 'none'" in csp
        assert client.get("/api/health/live").headers["content-security-policy"] == csp
        manifest = client.get("/manifest.webmanifest")
        assert manifest.status_code == 200
        assert manifest.headers["content-type"].startswith("application/manifest+json")
        assert client.get("/js/main.js").status_code == 200
        font = client.get("/fonts/inter-latin-wght-normal.woff2")
        assert font.status_code == 200
        assert font.headers["content-type"] == "font/woff2"
        assert client.get("/css/tokens.css").status_code == 200


def test_swagger_is_not_covered_by_strict_csp_outside_production(tmp_path: Path) -> None:
    settings = Settings(database_path=tmp_path / "n.db", frontend_path=tmp_path / "x")
    with TestClient(create_app(settings)) as client:
        assert "content-security-policy" not in client.get("/docs").headers
