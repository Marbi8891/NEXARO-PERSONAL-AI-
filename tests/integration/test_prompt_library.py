"""Biblioteca de prompts (ADR-0024): CRUD, versiones, catálogo, renderizado, aislamiento y roles."""

from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient

from nexaro_core.database import Database
from products.personal_ai import prompt_library as svc
from tests.conftest import ORIGIN, PASSWORD, FakeProvider, audit_actions

HEADERS = {"Origin": ORIGIN}
Factory = Callable[..., TestClient]
BODY = {
    "name": "Revisor de código",
    "category": "Software",
    "tags": ["Python", " python ", "Review"],
    "system_prompt": "Eres un revisor estricto.",
    "user_template": "Revisa este código en {{ lenguaje }}:\n{{codigo}}",
    "variables": [
        {"name": "lenguaje", "default": "Python"},
        {"name": "codigo", "type": "textarea", "required": True},
    ],
}


def setup_org(logged_in: Factory, slug: str = "acme") -> tuple[TestClient, str]:
    admin = logged_in("owner@example.com", role="admin")
    org = admin.post("/api/organizations", json={"name": slug, "slug": slug}, headers=HEADERS)
    return admin, str(org.json()["id"])


def create(client: TestClient, org: str, **overrides: object) -> dict:
    response = client.post(
        f"/api/organizations/{org}/prompts", json={**BODY, **overrides}, headers=HEADERS
    )
    assert response.status_code == 201, response.text
    return dict(response.json())


def login_as(app: object, email: str) -> TestClient:
    client = TestClient(app)  # type: ignore[arg-type]
    client.post("/api/auth/login", json={"email": email, "password": PASSWORD}, headers=HEADERS)
    return client


def test_create_normalizes_and_versions(logged_in: Factory, database: Database) -> None:
    admin, org = setup_org(logged_in)
    created = create(admin, org)
    assert created["tags"] == ["python", "review"] and created["version"] == 1
    assert [v["name"] for v in created["variables"]] == ["lenguaje", "codigo"]

    path = f"/api/organizations/{org}/prompts/{created['id']}"
    updated = admin.patch(
        path, json={"name": "Revisor v2", "changelog": "Nombre"}, headers=HEADERS
    ).json()
    assert updated["name"] == "Revisor v2" and updated["version"] == 2

    history = admin.get(f"{path}/versions").json()["items"]
    assert [(v["version"], v["changelog"]) for v in history] == [
        (2, "Nombre"),
        (1, "Versión inicial"),
    ]

    restored = admin.post(f"{path}/versions/1/restore", headers=HEADERS).json()
    assert restored["name"] == "Revisor de código" and restored["version"] == 3
    assert admin.post(f"{path}/versions/99/restore", headers=HEADERS).status_code == 404
    assert {"prompt.create", "prompt.update", "prompt.restore"} <= set(audit_actions(database))


@pytest.mark.parametrize(
    "overrides",
    [
        {"name": "x"},
        {"category": ""},
        {"user_template": "   "},
        {"user_template": "Hola {{sin_declarar}}"},
        {"variables": [{"name": 'x"><img src=x onerror=alert(1)>'}]},
        {"variables": [{"name": "a"}, {"name": "a"}]},
        {"variables": [{"name": "a", "type": "script"}]},
        {"tags": ["x" * 41]},
    ],
)
def test_invalid_prompts_are_rejected(logged_in: Factory, overrides: dict) -> None:
    admin, org = setup_org(logged_in)
    response = admin.post(
        f"/api/organizations/{org}/prompts", json={**BODY, **overrides}, headers=HEADERS
    )
    assert response.status_code == 422, overrides
    assert admin.get(f"/api/organizations/{org}/prompts").json()["total"] == 0


def test_search_filters_and_delete(logged_in: Factory) -> None:
    admin, org = setup_org(logged_in)
    first = create(admin, org)
    create(
        admin,
        org,
        name="Resumen",
        category="Escritura",
        tags=["texto"],
        variables=[],
        user_template="Resume: 50% del texto",
    )
    base = f"/api/organizations/{org}/prompts"
    assert admin.get(base).json()["categories"] == ["Escritura", "Software"]
    assert [p["name"] for p in admin.get(f"{base}?q=50%25").json()["items"]] == ["Resumen"]
    assert admin.get(f"{base}?q=_").json()["total"] == 0  # comodines escapados
    assert admin.get(f"{base}?tag=python").json()["total"] == 1
    assert admin.get(f"{base}?category=Software").json()["total"] == 1

    assert admin.delete(f"{base}/{first['id']}", headers=HEADERS).status_code == 204
    assert admin.get(f"{base}/{first['id']}").status_code == 404
    assert admin.get(f"{base}/{first['id']}/versions").status_code == 404


def test_render_then_chat_uses_the_real_chat_pipeline(
    logged_in: Factory, provider: FakeProvider
) -> None:
    admin, org = setup_org(logged_in)
    prompt = create(admin, org)
    path = f"/api/organizations/{org}/prompts/{prompt['id']}/render"

    missing = admin.post(path, json={"values": {}}, headers=HEADERS)
    assert missing.status_code == 422
    assert missing.json()["detail"] == "Faltan variables: codigo"

    rendered = admin.post(
        path, json={"values": {"codigo": "print({{lenguaje}})"}}, headers=HEADERS
    ).json()
    # Los valores son literales: un {{...}} dentro de un valor no se vuelve a sustituir.
    assert rendered["message"].endswith("Revisa este código en Python:\nprint({{lenguaje}})")
    assert rendered["message"].startswith("Instrucciones del prompt «Revisor de código»:")

    chat = admin.post("/api/chat", json={"message": rendered["message"]}, headers=HEADERS)
    assert chat.status_code == 200, chat.text
    sent = provider.requests[-1]
    assert sent.messages[0].role == "system" and "NEXARO" in sent.messages[0].content
    assert sent.messages[-1].content == rendered["message"]


def test_render_rejects_messages_longer_than_the_chat_allows(logged_in: Factory) -> None:
    admin, org = setup_org(logged_in)
    prompt = create(admin, org)
    response = admin.post(
        f"/api/organizations/{org}/prompts/{prompt['id']}/render",
        json={"values": {"codigo": "x" * 12_500}},
        headers=HEADERS,
    )
    assert response.status_code == 422 and "máximo del chat" in response.json()["detail"]


def test_catalogue_install_is_idempotent(logged_in: Factory, database: Database) -> None:
    admin, org = setup_org(logged_in)
    catalogue = admin.get("/api/prompt-catalogue").json()
    assert catalogue["total"] == 100 and "Cybersecurity" in catalogue["categories"]
    entry_id = catalogue["items"][0]["id"]

    path = f"/api/organizations/{org}/prompts/install"
    first = admin.post(path, json={"catalogue_id": entry_id}, headers=HEADERS)
    again = admin.post(path, json={"catalogue_id": entry_id}, headers=HEADERS)
    assert first.status_code == 201 and first.json()["installed_now"] is True
    assert again.json()["installed_now"] is False and again.json()["id"] == first.json()["id"]
    assert admin.get(f"/api/organizations/{org}/prompts").json()["total"] == 1
    assert admin.post(path, json={"catalogue_id": "no-existe"}, headers=HEADERS).status_code == 404
    assert admin.post(path, json={"catalogue_id": "../x"}, headers=HEADERS).status_code == 422
    assert audit_actions(database).count("prompt.install") == 1


def test_every_catalogue_entry_is_valid() -> None:
    for entry in svc.catalogue():
        svc.validate(entry)  # lanza PromptError si alguna entrada del catálogo no es válida


def test_prompts_are_isolated_between_organizations(logged_in: Factory) -> None:
    admin, acme = setup_org(logged_in)
    beta = admin.post(
        "/api/organizations", json={"name": "Beta", "slug": "beta"}, headers=HEADERS
    ).json()["id"]
    prompt = create(admin, acme)
    other = f"/api/organizations/{beta}/prompts/{prompt['id']}"
    assert admin.get(f"/api/organizations/{beta}/prompts").json()["total"] == 0
    assert admin.get(other).status_code == 404
    assert admin.patch(other, json={"name": "robado"}, headers=HEADERS).status_code == 404
    assert admin.delete(other, headers=HEADERS).status_code == 404
    assert admin.post(f"{other}/render", json={"values": {}}, headers=HEADERS).status_code == 404
    assert admin.post(f"{other}/versions/1/restore", headers=HEADERS).status_code == 404
    assert admin.get(f"/api/organizations/{acme}/prompts/{prompt['id']}").status_code == 200


def test_roles_viewer_reads_member_writes_outsider_sees_nothing(
    logged_in: Factory, add_user: Callable
) -> None:
    admin, org = setup_org(logged_in)
    prompt = create(admin, org)
    for email, role in (("m@example.com", "member"), ("v@example.com", "viewer")):
        add_user(email)
        admin.post(
            f"/api/organizations/{org}/members",
            json={"email": email, "role": role},
            headers=HEADERS,
        )
    base = f"/api/organizations/{org}/prompts"

    viewer = login_as(admin.app, "v@example.com")
    assert viewer.get(base).json()["total"] == 1
    assert (
        viewer.post(
            f"{base}/{prompt['id']}/render", json={"values": {"codigo": "x"}}, headers=HEADERS
        ).status_code
        == 200
    )
    assert viewer.post(base, json=BODY, headers=HEADERS).status_code == 403
    assert viewer.delete(f"{base}/{prompt['id']}", headers=HEADERS).status_code == 403

    member = login_as(admin.app, "m@example.com")
    assert member.post(base, json=BODY, headers=HEADERS).status_code == 201

    outsider = logged_in("out@example.com")
    assert outsider.get(base).status_code == 404
    assert TestClient(admin.app).get(base).status_code == 401
    assert TestClient(admin.app).get("/api/prompt-catalogue").status_code == 401


def test_writes_require_a_trusted_origin(logged_in: Factory) -> None:
    admin, org = setup_org(logged_in)
    response = admin.post(
        f"/api/organizations/{org}/prompts", json=BODY, headers={"Origin": "https://evil.example"}
    )
    assert response.status_code == 403


def test_catalogue_file_is_not_gitignored() -> None:
    """El catálogo viaja con el código: si .gitignore lo excluye, CI y Docker no lo tienen."""
    import shutil
    import subprocess

    git = shutil.which("git")
    if git is None:
        pytest.skip("git no disponible")
    result = subprocess.run(  # noqa: S603  # nosec B603
        [git, "check-ignore", "-q", str(svc.CATALOGUE_PATH)],
        cwd=svc.CATALOGUE_PATH.parent,
        check=False,
    )
    assert result.returncode == 1, f"{svc.CATALOGUE_PATH} está ignorado por git"
