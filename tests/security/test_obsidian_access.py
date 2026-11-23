"""Acceso al Vault de Obsidian: quién lo lee, rutas fuera del Vault y abuso de recursos.

Hallazgos OBS-1..OBS-4 de SECURITY_REVIEW_V1.md.
"""

from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from nexaro_api.main import create_app
from nexaro_core.config import Settings
from nexaro_core.obsidian.vault import ObsidianVault, VaultNoteTooLargeError
from tests.conftest import ORIGIN, FakeProvider, audit_actions

pytestmark = pytest.mark.security


@pytest.fixture
def vault_dir(tmp_path: Path) -> Path:
    root = tmp_path / "vault"
    (root / "DAW").mkdir(parents=True)
    (root / "DAW" / "nota.md").write_text("# Nota\n\ncontenido privado #daw", encoding="utf-8")
    (tmp_path / "fuera.md").write_text("secreto fuera del vault", encoding="utf-8")
    return root


@pytest.fixture
def settings(tmp_path: Path, vault_dir: Path) -> Settings:
    return Settings(
        database_path=tmp_path / "nexaro.db",
        frontend_path=tmp_path / "sin-frontend",
        allowed_origins=frozenset({ORIGIN}),
        obsidian_vault_path=str(vault_dir),
        obsidian_allowed_emails=frozenset({"Invitada@Example.com"}),
        obsidian_max_note_bytes=1024,
        obsidian_requests_per_minute=5,
    )


@pytest.fixture
def app(settings: Settings, provider: FakeProvider) -> Any:
    return create_app(settings, chat_provider=provider)


@pytest.fixture
def client(app: Any) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


ENDPOINTS = (
    "/api/obsidian/status",
    "/api/obsidian/notes",
    "/api/obsidian/note/DAW/nota.md",
    "/api/obsidian/search?q=privado",
)


@pytest.mark.parametrize("path", ENDPOINTS)
def test_anonymous_users_cannot_reach_the_vault(client: TestClient, path: str) -> None:
    assert client.get(path).status_code == 401


@pytest.mark.parametrize("path", ENDPOINTS)
def test_regular_users_cannot_read_the_owners_vault(
    logged_in: Callable[..., TestClient], path: str, database: Any
) -> None:
    user = logged_in("normal@example.com")
    response = user.get(path)
    assert response.status_code == 403
    assert "privado" not in response.text
    assert "obsidian.access" in audit_actions(database)


def test_admin_and_allowlisted_account_can_read(logged_in: Callable[..., TestClient]) -> None:
    admin = logged_in("admin@example.com", role="admin")
    guest = logged_in("invitada@example.com")  # comparación sin distinguir mayúsculas
    for client in (admin, guest):
        assert client.get("/api/obsidian/note/DAW/nota.md").json()["content"].startswith("# Nota")
        assert client.get("/api/obsidian/search?q=privado").json()["results"]


@pytest.mark.parametrize(
    "note",
    [
        "../fuera.md",
        "DAW/../../fuera.md",
        "%2e%2e/fuera.md",
        "..%2ffuera.md",
        "DAW/..%5c..%5cfuera.md",
        ".obsidian/workspace.md",
    ],
)
def test_traversal_never_leaves_the_vault(logged_in: Callable[..., TestClient], note: str) -> None:
    admin = logged_in("admin@example.com", role="admin")
    response = admin.get(f"/api/obsidian/note/{note}")
    assert response.status_code in (404, 422)
    assert "secreto" not in response.text


def test_absolute_paths_are_rejected(tmp_path: Path, vault_dir: Path) -> None:
    vault = ObsidianVault(vault_dir)
    for absolute in (str(tmp_path / "fuera.md"), "/etc/passwd", "\\\\server\\share\\x.md"):
        with pytest.raises(ValueError):
            vault.read_note(absolute)


def test_large_notes_are_refused_and_skipped_by_search(
    logged_in: Callable[..., TestClient], vault_dir: Path
) -> None:
    (vault_dir / "enorme.md").write_text("privado " * 1000, encoding="utf-8")
    admin = logged_in("admin@example.com", role="admin")
    assert admin.get("/api/obsidian/note/enorme.md").status_code == 413
    paths = [r["path"] for r in admin.get("/api/obsidian/search?q=privado").json()["results"]]
    assert paths == ["DAW/nota.md"]
    listed = {n["path"]: n for n in admin.get("/api/obsidian/notes").json()["notes"]}
    assert listed["enorme.md"]["tags"] == []  # no se lee para extraer etiquetas


def test_read_limit_does_not_load_the_whole_file(vault_dir: Path) -> None:
    (vault_dir / "grande.md").write_bytes(b"x" * 5000)
    vault = ObsidianVault(vault_dir, max_note_bytes=100)
    with pytest.raises(VaultNoteTooLargeError):
        vault.read_note("grande.md")


def test_scans_stop_at_the_file_limit(vault_dir: Path) -> None:
    for i in range(20):
        (vault_dir / f"n{i:02}.md").write_text("aguja", encoding="utf-8")
    vault = ObsidianVault(vault_dir, max_files=5)
    status = vault.status()
    assert status["note_count"] == 5 and status["truncated"] is True
    assert len(vault.list_notes()) == 5
    assert len(vault.search("aguja", limit=100)) <= 5


def test_vault_reads_are_rate_limited_per_user(logged_in: Callable[..., TestClient]) -> None:
    admin = logged_in("admin@example.com", role="admin")
    guest = logged_in("invitada@example.com")
    codes = [admin.get("/api/obsidian/status").status_code for _ in range(6)]
    assert codes[:5] == [200] * 5 and codes[5] == 429
    assert guest.get("/api/obsidian/status").status_code == 200  # otro usuario, otro cupo


def test_unconfigured_vault_does_not_fall_back_to_the_environment(
    logged_in: Callable[..., TestClient],
    tmp_path: Path,
    vault_dir: Path,
    provider: FakeProvider,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBSIDIAN_VAULT_PATH", str(vault_dir))
    settings = Settings(
        database_path=tmp_path / "otra.db",
        frontend_path=tmp_path / "sin-frontend",
        allowed_origins=frozenset({ORIGIN}),
        obsidian_vault_path=None,
    )
    # La configuración explícita manda: Settings(...) con None ignora el entorno.
    assert settings.obsidian_vault_path is None
    with TestClient(create_app(settings, chat_provider=provider)) as client:
        from nexaro_core.database import Database
        from nexaro_core.identity import create_user
        from tests.conftest import PASSWORD, login

        with Database(settings.database_path).connect() as db:
            uid = create_user(db, "root@example.com", PASSWORD, approved=True)
            db.execute("UPDATE users SET role = 'admin' WHERE id = ?", (uid,))
        assert login(client, "root@example.com").status_code == 200
        assert client.get("/api/obsidian/status").json()["configured"] is False
