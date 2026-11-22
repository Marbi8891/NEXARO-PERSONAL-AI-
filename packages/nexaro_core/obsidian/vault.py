"""Read-only Obsidian Vault connector for NEXARO."""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

DEFAULT_EXCLUDED_DIRS = frozenset({".obsidian", ".trash", ".git", "node_modules"})


class VaultNotConfiguredError(RuntimeError):
    """Raised when the Vault path is not configured or unavailable."""


class VaultPathError(ValueError):
    """Raised when a requested note path is invalid or outside the Vault."""


class ObsidianVault:
    """Minimal, read-only access to Markdown notes in a local Obsidian Vault."""

    def __init__(self, vault_path: str | Path | None = None) -> None:
        configured = vault_path if vault_path is not None else os.getenv("OBSIDIAN_VAULT_PATH")
        self.path = Path(configured).expanduser() if configured else None

    def _root(self) -> Path:
        if self.path is None:
            raise VaultNotConfiguredError("OBSIDIAN_VAULT_PATH no está configurado")
        root = self.path.resolve()
        if not root.is_dir():
            raise VaultNotConfiguredError("La ruta configurada no es un Vault accesible")
        return root

    @staticmethod
    def _is_excluded(relative: Path) -> bool:
        return any(part in DEFAULT_EXCLUDED_DIRS or part.startswith(".") for part in relative.parts)

    @staticmethod
    def _within_root(root: Path, candidate: Path) -> bool:
        try:
            candidate.resolve().relative_to(root)
            return True
        except ValueError:
            return False

    def _iter_notes(self, root: Path):
        for candidate in root.rglob("*.md"):
            relative = candidate.relative_to(root)
            if not candidate.is_file() or self._is_excluded(relative):
                continue
            if not self._within_root(root, candidate):
                continue
            yield candidate, relative

    def status(self) -> dict[str, Any]:
        if self.path is None:
            return {"configured": False, "available": False, "note_count": 0}
        try:
            root = self._root()
        except VaultNotConfiguredError:
            return {"configured": True, "available": False, "note_count": 0}
        return {"configured": True, "available": True, "note_count": sum(1 for _ in self._iter_notes(root))}

    def list_notes(self, *, limit: int = 200, offset: int = 0) -> list[dict[str, Any]]:
        root = self._root()
        notes = sorted((relative.as_posix(), candidate) for candidate, relative in self._iter_notes(root))
        selected = notes[offset : offset + limit]
        return [self._metadata(candidate, relative) for relative, candidate in selected]

    def read_note(self, note_path: str) -> dict[str, Any]:
        root = self._root()
        target = self._resolve_note(root, note_path)
        content = target.read_text(encoding="utf-8")
        return {"path": target.relative_to(root).as_posix(), "content": content}

    def search(self, query: str, *, limit: int = 20) -> list[dict[str, Any]]:
        root = self._root()
        needle = query.strip().casefold()
        if not needle:
            return []
        results: list[dict[str, Any]] = []
        for candidate, relative in self._iter_notes(root):
            try:
                content = candidate.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            index = content.casefold().find(needle)
            if index < 0:
                continue
            start = max(0, index - 100)
            end = min(len(content), index + len(query) + 180)
            snippet = content[start:end].replace("\n", " ").strip()
            results.append({
                "path": relative.as_posix(),
                "title": self._title(content, candidate.stem),
                "snippet": snippet,
            })
            if len(results) >= limit:
                break
        return results

    def _resolve_note(self, root: Path, note_path: str) -> Path:
        if not note_path or "\x00" in note_path:
            raise VaultPathError("Ruta de nota no válida")
        requested = Path(note_path)
        if requested.is_absolute():
            raise VaultPathError("No se permiten rutas absolutas")
        target = (root / requested).resolve()
        try:
            relative = target.relative_to(root)
        except ValueError as exc:
            raise VaultPathError("La ruta está fuera del Vault") from exc
        if self._is_excluded(relative):
            raise VaultPathError("Ruta excluida")
        if target.suffix.lower() != ".md" or not target.is_file():
            raise VaultPathError("La nota no existe o no es Markdown")
        return target

    @staticmethod
    def _title(content: str, fallback: str) -> str:
        match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
        return match.group(1).strip() if match else fallback

    @classmethod
    def _metadata(cls, file_path: Path, relative: str) -> dict[str, Any]:
        try:
            content = file_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            content = ""
        tags = sorted(set(re.findall(r"(?<![\w])#([\w/-]+)", content)))
        return {
            "path": relative,
            "title": cls._title(content, file_path.stem),
            "tags": tags,
            "size_bytes": file_path.stat().st_size,
        }
