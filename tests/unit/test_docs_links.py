"""La documentación no debe tener enlaces relativos rotos (scripts/check_docs_links.py)."""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    "check_docs_links", ROOT / "scripts" / "check_docs_links.py"
)
assert _spec and _spec.loader
links = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(links)


def test_repository_docs_have_no_broken_links() -> None:
    assert links.broken_links(ROOT) == []


def test_detects_missing_file_and_missing_anchor(tmp_path: Path) -> None:
    (tmp_path / "a.md").write_text(
        "# Título uno\n\n[ok](b.md#sección) [x](nada.md) [y](b.md#otra)\n"
    )
    (tmp_path / "b.md").write_text("## Sección\n")
    assert sorted(links.broken_links(tmp_path)) == [
        "a.md: no existe el ancla b.md#otra",
        "a.md: no existe nada.md",
    ]


def test_ignores_urls_and_code_blocks(tmp_path: Path) -> None:
    (tmp_path / "a.md").write_text(
        "[w](https://example.com) [m](mailto:x@example.com)\n```\n[r](nada.md)\n```\n"
    )
    assert links.broken_links(tmp_path) == []
