"""ADR-0001: las reglas de dependencia del monolito modular se comprueban, no se confían."""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PRODUCT_NAMES = {
    p.name for p in (ROOT / "products").iterdir() if p.is_dir() and not p.name.startswith("_")
}


def imports(path: Path) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.add(node.module)
    return found


def violations(files: list[Path], forbidden: set[str]) -> list[str]:
    return [
        f"{f.relative_to(ROOT)} importa {module}"
        for f in files
        for module in imports(f)
        if module.split(".")[0] in forbidden
    ]


def test_packages_do_not_depend_on_products_or_apps() -> None:
    files = list((ROOT / "packages").rglob("*.py"))
    assert files
    assert violations(files, {"products", "nexaro_api"}) == []


def test_products_do_not_depend_on_apps_or_each_other() -> None:
    for product in PRODUCT_NAMES:
        files = list((ROOT / "products" / product).rglob("*.py"))
        other = {f"products.{p}" for p in PRODUCT_NAMES if p != product}
        bad = [
            f"{f.relative_to(ROOT)} importa {m}"
            for f in files
            for m in imports(f)
            if m.split(".")[0] == "nexaro_api"
            or any(m == o or m.startswith(o + ".") for o in other)
        ]
        assert bad == []


def test_domain_modules_do_not_import_fastapi() -> None:
    files = list((ROOT / "packages" / "nexaro_core").rglob("*.py")) + list(
        (ROOT / "products").rglob("*.py")
    )
    assert violations(files, {"fastapi", "starlette"}) == []
