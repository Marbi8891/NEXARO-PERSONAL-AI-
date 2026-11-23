"""Comprueba que los enlaces relativos de la documentación Markdown apuntan a algo que existe.

Valida enlaces `[texto](ruta)`, `src="..."`/`href="..."` y anclas `#encabezado` hacia otros
Markdown.
Ignora URLs absolutas (http, mailto...) y los bloques de código. Solo biblioteca estándar.

Uso: python scripts/check_docs_links.py [raíz]   (código de salida 1 si hay enlaces rotos)
"""

from __future__ import annotations

import os
import re
import sys
from functools import cache
from pathlib import Path

SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "_to_delete", ".terraform", "eval-out"}
CODE_BLOCK = re.compile(r"```.*?```", re.S)
LINK = re.compile(r"\]\(([^)\s]+)\)|(?:src|href)=\"([^\"]+)\"")
HEADING = re.compile(r"^#{1,6}\s+(.*)$", re.M)
INLINE_MARKUP = re.compile(r"[`*_]|\[([^\]]*)\]\([^)]*\)")


def slug(heading: str) -> str:
    """Ancla al estilo de GitHub: minúsculas, sin puntuación, espacios a guiones."""
    text = INLINE_MARKUP.sub(r"\1", heading).strip().lower()
    return re.sub(r"[^\w\- ]", "", text).replace(" ", "-")


@cache
def anchors(path: Path) -> frozenset[str]:
    text = CODE_BLOCK.sub("", path.read_text(encoding="utf-8"))
    return frozenset(slug(h) for h in HEADING.findall(text))


def markdown_files(root: Path) -> list[Path]:
    found = []
    for directory, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        found += [Path(directory) / f for f in files if f.endswith(".md")]
    return sorted(found)


def broken_links(root: Path) -> list[str]:
    problems = []
    for path in markdown_files(root):
        text = CODE_BLOCK.sub("", path.read_text(encoding="utf-8"))
        for match in LINK.finditer(text):
            target = match.group(1) or match.group(2)
            if re.match(r"^[a-z][a-z0-9+.-]*:", target) or target.startswith("/"):
                continue
            file_part, _, fragment = target.partition("#")
            dest = path if not file_part else (path.parent / file_part).resolve()
            where = path.relative_to(root)
            if not dest.exists():
                problems.append(f"{where}: no existe {target}")
            elif fragment and dest.suffix == ".md" and fragment not in anchors(dest):
                problems.append(f"{where}: no existe el ancla {target}")
    return problems


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    problems = broken_links(root)
    for problem in problems:
        print(problem)
    print(f"{len(markdown_files(root))} archivos Markdown, {len(problems)} enlaces rotos")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
