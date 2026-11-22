"""Aislamiento estricto de conversaciones por usuario (docs/security/CONVERSATION_ISOLATION.md).

Dos usuarios independientes (USER_A, USER_B), cada uno con su conversación. Toda petición de A
sobre lo de B tiene que fallar exactamente igual que sobre algo que no existe, sin efectos.
"""

import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from nexaro_api.bootstrap import all_migrations
from nexaro_core.database import Database, run_migrations
from nexaro_core.organizations import create_organization
from tests.conftest import HEADERS, FakeProvider

pytestmark = pytest.mark.security

Factory = Callable[..., TestClient]
SECRET_A = "texto-exclusivo-de-alice-7f3a"
SECRET_B = "texto-exclusivo-de-bob-91c2"
MISSING = "00000000-0000-4000-8000-000000000000"
ROOT = Path(__file__).resolve().parents[2]


@dataclass
class Pair:
    a: TestClient
    b: TestClient
    a_id: str
    b_id: str
    conv_a: str
    conv_b: str


def start(client: TestClient, message: str) -> str:
    response = client.post("/api/chat", json={"message": message}, headers=HEADERS)
    assert response.status_code == 200, response.text
    return str(response.json()["conversation_id"])


def me(client: TestClient) -> str:
    return str(client.get("/api/auth/me").json()["user"]["id"])


@pytest.fixture
def pair(logged_in: Factory) -> Pair:
    a, b = logged_in("user_a@example.com"), logged_in("user_b@example.com")
    return Pair(a, b, me(a), me(b), start(a, SECRET_A), start(b, SECRET_B))


def messages_of(database: Database, conversation_id: str) -> list[str]:
    with database.connect() as db:
        rows = db.execute(
            "SELECT content FROM messages WHERE conversation_id = ? ORDER BY id", (conversation_id,)
        ).fetchall()
    return [r["content"] for r in rows]


def owner_of(database: Database, conversation_id: str) -> str | None:
    with database.connect() as db:
        row = db.execute(
            "SELECT user_id FROM conversations WHERE id = ?", (conversation_id,)
        ).fetchone()
    return None if row is None else row["user_id"]


def assert_hidden(response: Any, *leaks: str) -> None:
    """404 genérico: ni contenido, ni propietario, ni pista de que exista."""
    assert response.status_code == 404, response.text
    assert response.json() == {"detail": "Conversación no encontrada"}
    for leak in leaks:
        assert leak not in response.text


# ---- Tests 1-2: listados -------------------------------------------------------------------


def test_01_user_a_lists_only_conversation_a(pair: Pair) -> None:
    listed = pair.a.get("/api/conversations").json()["conversations"]
    assert [c["id"] for c in listed] == [pair.conv_a]
    assert SECRET_B not in str(listed)


def test_02_user_b_lists_only_conversation_b(pair: Pair) -> None:
    listed = pair.b.get("/api/conversations").json()["conversations"]
    assert [c["id"] for c in listed] == [pair.conv_b]
    assert SECRET_A not in str(listed)


def test_dashboard_activity_only_counts_own_conversations(pair: Pair) -> None:
    activity = pair.a.get("/api/dashboard").json()["activity"]
    assert activity["conversations"] == 1
    assert [c["id"] for c in activity["recent"]] == [pair.conv_a]
    assert SECRET_B not in str(activity)


# ---- Tests 3-4: lectura de la conversación y de sus mensajes -------------------------------


def test_03_and_04_user_a_cannot_read_conversation_b_or_its_messages(pair: Pair) -> None:
    foreign = pair.a.get(f"/api/conversations/{pair.conv_b}")
    assert_hidden(foreign, SECRET_B, pair.b_id)
    # Indistinguible de un id inexistente (no se revela que existe).
    missing = pair.a.get(f"/api/conversations/{MISSING}")
    assert (foreign.status_code, foreign.json()) == (missing.status_code, missing.json())


def test_owner_still_reads_own_conversation(pair: Pair) -> None:
    data = pair.b.get(f"/api/conversations/{pair.conv_b}").json()
    assert data["conversation"]["id"] == pair.conv_b
    assert SECRET_B in [m["content"] for m in data["messages"]]


# ---- Test 5: añadir mensajes ---------------------------------------------------------------


@pytest.mark.parametrize("path", ["/api/chat", "/api/chat/stream"])
def test_05_user_a_cannot_add_messages_to_conversation_b(
    pair: Pair, database: Database, provider: FakeProvider, path: str
) -> None:
    before = messages_of(database, pair.conv_b)
    calls = len(provider.requests)
    response = pair.a.post(
        path, json={"message": "intruso", "conversation_id": pair.conv_b}, headers=HEADERS
    )
    assert_hidden(response, SECRET_B)
    assert messages_of(database, pair.conv_b) == before
    # El modelo nunca recibe el historial ajeno (ni se le llama).
    assert len(provider.requests) == calls


# ---- Tests 6-8: modificar, borrar y exportar -----------------------------------------------


@pytest.mark.parametrize("method", ["put", "patch", "post"])
def test_06_user_a_cannot_modify_conversation_b(
    pair: Pair, database: Database, method: str
) -> None:
    before = messages_of(database, pair.conv_b)
    response = getattr(pair.a, method)(
        f"/api/conversations/{pair.conv_b}",
        json={"title": "hackeado", "user_id": pair.a_id},
        headers=HEADERS,
    )
    # No hay ruta de edición: el método no está permitido. Nada cambia en ningún caso.
    assert response.status_code in (404, 405)
    assert SECRET_B not in response.text
    assert messages_of(database, pair.conv_b) == before
    assert owner_of(database, pair.conv_b) == pair.b_id


def test_07_user_a_cannot_delete_conversation_b(pair: Pair, database: Database) -> None:
    response = pair.a.delete(f"/api/conversations/{pair.conv_b}", headers=HEADERS)
    assert_hidden(response)
    assert owner_of(database, pair.conv_b) == pair.b_id
    assert messages_of(database, pair.conv_b)
    assert pair.b.get(f"/api/conversations/{pair.conv_b}").status_code == 200


def test_07b_deleting_is_audited_only_for_the_owner(pair: Pair, database: Database) -> None:
    pair.a.delete(f"/api/conversations/{pair.conv_b}", headers=HEADERS)
    with database.connect() as db:
        assert not db.execute(
            "SELECT 1 FROM audit_events WHERE action = 'conversation.delete'"
        ).fetchall()
    assert pair.b.delete(f"/api/conversations/{pair.conv_b}", headers=HEADERS).status_code == 204
    assert owner_of(database, pair.conv_b) is None  # borrada de verdad


@pytest.mark.parametrize(
    "suffix", ["/export", "/export.json", "/export.md", "/messages", "/download"]
)
def test_08_user_a_cannot_export_conversation_b(pair: Pair, suffix: str) -> None:
    response = pair.a.get(f"/api/conversations/{pair.conv_b}{suffix}")
    assert response.status_code in (404, 405)
    assert SECRET_B not in response.text


# ---- Test 9: propietario manipulado en la petición -----------------------------------------


def test_09_owner_sent_by_client_is_ignored(pair: Pair, database: Database) -> None:
    response = pair.a.post(
        f"/api/chat?user_id={pair.b_id}",
        json={"message": "mía", "user_id": pair.b_id, "owner": pair.b_id},
        headers={**HEADERS, "X-User-Id": pair.b_id},
    )
    assert response.status_code == 200
    created = response.json()["conversation_id"]
    assert owner_of(database, created) == pair.a_id
    listed_b = pair.b.get("/api/conversations").json()["conversations"]
    assert created not in [c["id"] for c in listed_b]


def test_09b_client_chosen_ids_never_create_conversations(
    pair: Pair, database: Database, provider: FakeProvider
) -> None:
    """V-01: un id desconocido no crea nada. Sin esto, 200 (no existe) frente a 404 (existe y es
    ajena) revelaba la existencia de conversaciones de otros."""
    for conversation_id in (MISSING, "elegido-por-el-cliente", pair.conv_b):
        response = pair.a.post(
            "/api/chat",
            json={"message": "hola", "conversation_id": conversation_id},
            headers=HEADERS,
        )
        assert_hidden(response)
    assert owner_of(database, MISSING) is None
    assert owner_of(database, "elegido-por-el-cliente") is None


# ---- Test 10: sin autenticación ------------------------------------------------------------


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/api/conversations"),
        ("get", "/api/conversations/{b}"),
        ("delete", "/api/conversations/{b}"),
        ("post", "/api/chat"),
        ("post", "/api/chat/stream"),
        ("get", "/api/dashboard"),
        ("get", "/api/v1/conversations"),
        ("get", "/api/v1/conversations/{b}"),
        ("post", "/api/v1/chat"),
    ],
)
def test_10_unauthenticated_requests_get_401(
    pair: Pair, client: TestClient, method: str, path: str
) -> None:
    kwargs: dict[str, Any] = {"headers": HEADERS}
    if method == "post":
        kwargs["json"] = {"message": "hola", "conversation_id": pair.conv_b}
    anonymous = TestClient(client.app)  # sin cookies
    response = getattr(anonymous, method)(path.format(b=pair.conv_b), **kwargs)
    assert response.status_code == 401
    assert SECRET_B not in response.text


def test_10b_forged_or_revoked_session_gets_401(pair: Pair) -> None:
    forged = TestClient(pair.a.app, cookies={"nexaro_session": "inventada"})
    assert forged.get("/api/conversations").status_code == 401
    assert pair.a.post("/api/auth/logout", headers=HEADERS).status_code in (200, 204)
    assert pair.a.get(f"/api/conversations/{pair.conv_a}").status_code == 401


# ---- Test 11: búsqueda ---------------------------------------------------------------------


def make_org(database: Database, owner: str, slug: str) -> str:
    with database.connect() as db:
        return str(create_organization(db, slug, slug, owner)["id"])


def test_11_search_never_returns_other_users_messages(pair: Pair, database: Database) -> None:
    """No hay búsqueda de historial: el único texto «buscable» de un usuario es su propio
    listado (título y vista previa) y la búsqueda de documentos, siempre de su organización."""
    for client in (pair.a,):
        listed = client.get("/api/conversations", params={"q": SECRET_B, "user_id": pair.b_id})
        assert listed.status_code == 200
        assert [c["id"] for c in listed.json()["conversations"]] == [pair.conv_a]
        assert SECRET_B not in listed.text
    org = make_org(database, pair.a_id, "org-a")
    found = pair.a.get(f"/api/organizations/{org}/documents/search", params={"q": SECRET_B})
    assert found.status_code == 200 and found.json()["results"] == []


# ---- Test 12: accesos indirectos (documentos, claves de API, agentes, tareas) --------------


@pytest.fixture
def orgs(pair: Pair, database: Database) -> dict[str, str]:
    """Cada usuario con su organización y un documento con su texto secreto."""
    ids = {}
    for name, client, secret in (("a", pair.a, SECRET_A), ("b", pair.b, SECRET_B)):
        org = make_org(database, me(client), f"org-{name}")
        doc = client.post(
            f"/api/organizations/{org}/documents",
            json={"title": f"doc {name}", "content": f"Contenido {secret} confidencial."},
            headers=HEADERS,
        )
        assert doc.status_code == 201, doc.text
        ids[name], ids[f"doc_{name}"] = org, doc.json()["id"]
    return ids


def test_12a_user_a_cannot_reach_documents_of_user_b(pair: Pair, orgs: dict[str, str]) -> None:
    base = f"/api/organizations/{orgs['b']}/documents"
    attempts = [
        pair.a.get(base),
        pair.a.get(f"{base}/search", params={"q": SECRET_B}),
        pair.a.post(f"{base}/ask", json={"question": SECRET_B}, headers=HEADERS),
        pair.a.post(base, json={"title": "x", "content": "x"}, headers=HEADERS),
        pair.a.delete(f"{base}/{orgs['doc_b']}", headers=HEADERS),
        # Id de un documento de B dentro de la organización de A.
        pair.a.delete(f"/api/organizations/{orgs['a']}/documents/{orgs['doc_b']}", headers=HEADERS),
    ]
    for response in attempts:
        assert response.status_code == 404, response.text
        assert SECRET_B not in response.text
    own = pair.b.get(f"{base}/search", params={"q": SECRET_B}).json()["results"]
    assert own and SECRET_B in own[0]["snippet"]  # el documento sigue ahí, intacto


def test_12b_chat_cannot_pull_fragments_from_another_users_organization(
    pair: Pair, orgs: dict[str, str], provider: FakeProvider
) -> None:
    calls = len(provider.requests)
    response = pair.a.post(
        "/api/chat",
        json={"message": SECRET_B, "document_organization_id": orgs["b"]},
        headers=HEADERS,
    )
    assert response.status_code == 404
    assert len(provider.requests) == calls  # ningún fragmento llegó al modelo


def test_12c_api_keys_only_reach_their_creators_conversations(
    pair: Pair, orgs: dict[str, str]
) -> None:
    key = pair.a.post(
        f"/api/organizations/{orgs['a']}/api-keys",
        json={"name": "k", "scopes": ["chat:write", "conversations:read"]},
        headers=HEADERS,
    ).json()["secret"]
    bearer = {"Authorization": f"Bearer {key}"}
    api = TestClient(pair.a.app)
    assert api.get("/api/v1/conversations", headers=bearer).json()["conversations"] == []
    assert_hidden(api.get(f"/api/v1/conversations/{pair.conv_b}", headers=bearer), SECRET_B)
    # Ni las ajenas, ni las propias del chat web: la clave solo ve su propio origen.
    assert_hidden(api.get(f"/api/v1/conversations/{pair.conv_a}", headers=bearer), SECRET_A)
    for target in (pair.conv_b, pair.conv_a, MISSING):
        sent = api.post(
            "/api/v1/chat", json={"message": "x", "conversation_id": target}, headers=bearer
        )
        assert_hidden(sent, SECRET_B)


def test_12d_platform_admin_gets_no_access_to_private_content(
    pair: Pair, logged_in: Factory, orgs: dict[str, str]
) -> None:
    admin = logged_in("root@example.com", role="admin")
    assert_hidden(admin.get(f"/api/conversations/{pair.conv_b}"), SECRET_B)
    assert admin.get("/api/conversations").json()["conversations"] == []
    assert admin.delete(f"/api/conversations/{pair.conv_b}", headers=HEADERS).status_code == 404
    assert admin.get(f"/api/organizations/{orgs['b']}/documents").status_code == 404
    for path in ("/api/admin/audit", "/api/admin/users", "/api/admin/usage", "/api/dashboard"):
        response = admin.get(path)
        assert response.status_code == 200, path
        assert SECRET_A not in response.text and SECRET_B not in response.text, path


def test_12e_no_route_exposes_agents_tasks_or_embeddings_without_a_scoped_test(app: Any) -> None:
    """Inventario: toda ruta /api con un id en la ruta tiene que estar en esta lista, que está
    cubierta por los tests de arriba o por los de organización. Una ruta nueva (exportar,
    renombrar, agentes, tareas, WebSocket...) rompe este test hasta que se añada su prueba de
    aislamiento."""
    covered = {
        ("GET", "/api/conversations/{conversation_id}"),
        ("DELETE", "/api/conversations/{conversation_id}"),
        ("GET", "/api/v1/conversations/{conversation_id}"),
        ("GET", "/api/organizations/{organization_id}/documents"),
        ("POST", "/api/organizations/{organization_id}/documents"),
        ("POST", "/api/organizations/{organization_id}/documents/pdf"),
        ("DELETE", "/api/organizations/{organization_id}/documents/{document_id}"),
        ("GET", "/api/organizations/{organization_id}/documents/search"),
        ("POST", "/api/organizations/{organization_id}/documents/ask"),
        ("GET", "/api/organizations/{organization_id}/api-keys"),
        ("POST", "/api/organizations/{organization_id}/api-keys"),
        ("DELETE", "/api/organizations/{organization_id}/api-keys/{key_id}"),
        ("GET", "/api/organizations/{organization_id}/usage"),
        ("GET", "/api/organizations/{organization_id}/members"),
        ("POST", "/api/organizations/{organization_id}/members"),
        ("PATCH", "/api/organizations/{organization_id}/members/{user_id}"),
        ("DELETE", "/api/organizations/{organization_id}/members/{user_id}"),
        ("GET", "/api/organizations/{organization_id}/expenses"),
        ("POST", "/api/organizations/{organization_id}/expenses"),
        ("GET", "/api/organizations/{organization_id}/expenses/summary"),
        ("GET", "/api/organizations/{organization_id}/expenses/export.csv"),
        ("PATCH", "/api/organizations/{organization_id}/expenses/{expense_id}"),
        ("DELETE", "/api/organizations/{organization_id}/expenses/{expense_id}"),
        ("POST", "/api/admin/users/{user_id}/approve"),
        ("POST", "/api/admin/users/{user_id}/reject"),
        ("PATCH", "/api/admin/users/{user_id}/active"),
    }
    found = {
        (method, route.path)
        for route in app.routes
        if isinstance(route, APIRoute) and "{" in route.path
        for method in route.methods
    }
    assert found == covered, found ^ covered
    assert not [r for r in app.routes if type(r).__name__ == "APIWebSocketRoute"]


# ---- Base de datos: la propiedad la impone también el esquema ------------------------------


def test_schema_requires_an_owner_and_keeps_it(pair: Pair, database: Database) -> None:
    with database.connect() as db, pytest.raises(sqlite3.IntegrityError, match="obligatorio"):
        db.execute("INSERT INTO conversations (id) VALUES ('sin-dueno')")
    with database.connect() as db, pytest.raises(sqlite3.IntegrityError, match="no se puede"):
        db.execute("UPDATE conversations SET user_id = ? WHERE id = ?", (pair.a_id, pair.conv_b))
    with database.connect() as db, pytest.raises(sqlite3.IntegrityError, match="no se puede"):
        db.execute("UPDATE conversations SET user_id = NULL WHERE id = ?", (pair.conv_b,))
    assert owner_of(database, pair.conv_b) == pair.b_id


def test_legacy_orphans_survive_the_migration_untouched_and_invisible(
    tmp_path: Path, logged_in: Factory
) -> None:
    """Una base con conversaciones sin propietario (anterior a la 0007): la migración no borra ni
    asigna nada; las huérfanas no las ve nadie (ni el admin) y no admiten mensajes nuevos."""
    database = Database(tmp_path / "legacy.db")
    database.ensure_parent()
    migrations = all_migrations()
    run_migrations(database, migrations[:6])
    with database.connect() as db:
        db.execute("INSERT INTO conversations (id) VALUES ('huerfana')")
        db.execute(
            "INSERT INTO messages (conversation_id, role, content) VALUES ('huerfana', 'user', ?)",
            ("dato antiguo",),
        )
    assert run_migrations(database, migrations) == [7]
    with database.connect() as db:
        assert db.execute("SELECT user_id FROM conversations").fetchall()[0]["user_id"] is None
        assert db.execute("SELECT COUNT(*) AS n FROM messages").fetchone()["n"] == 1
        with pytest.raises(sqlite3.IntegrityError, match="propietario"):
            db.execute(
                "INSERT INTO messages (conversation_id, role, content)"
                " VALUES ('huerfana', 'user', 'x')"
            )
        # Recuperación explícita (NULL -> usuario): la única transferencia permitida.
        db.execute("INSERT INTO users (id, email, password_hash) VALUES ('u1', 'u@x.es', 'h')")
        db.execute("UPDATE conversations SET user_id = 'u1' WHERE id = 'huerfana'")


def test_orphan_recovery_via_bootstrap_admin_is_audited(tmp_path: Path) -> None:
    from tests.integration.test_bootstrap_admin import run_cli
    from tests.legacy_db import LEGACY_EMAIL, create_legacy_database

    path = tmp_path / "nexaro.db"
    create_legacy_database(path)
    with sqlite3.connect(path) as db:  # base anterior a la 0007: aún admite huérfanas
        db.execute("INSERT INTO conversations (id, user_id) VALUES ('huerfana', NULL)")
    result = run_cli(
        path, "--email", LEGACY_EMAIL, "--promote-existing", "--assign-orphaned-conversations"
    )
    assert result.returncode == 0, result.stderr
    assert "Conversaciones asignadas: 1" in result.stdout
    with sqlite3.connect(path) as db:
        rows = db.execute(
            "SELECT details FROM audit_events WHERE action = 'conversation.orphans_assigned'"
        ).fetchall()
    assert len(rows) == 1 and '"assigned": 1' in rows[0][0]
