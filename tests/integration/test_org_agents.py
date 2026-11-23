"""Agentes de organización (ADR-0024): permisos por rol, aislamiento entre organizaciones,
pérdida de acceso al salir y uso real en el chat."""

from collections.abc import Callable
from typing import Any

from fastapi.testclient import TestClient

from nexaro_core.database import Database
from tests.conftest import HEADERS, FakeProvider, audit_actions

Factory = Callable[..., TestClient]


def create_org(owner: TestClient, slug: str = "acme") -> str:
    response = owner.post(
        "/api/organizations", json={"name": slug.title(), "slug": slug}, headers=HEADERS
    )
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


def add(owner: TestClient, org: str, email: str, role: str) -> str:
    response = owner.post(
        f"/api/organizations/{org}/members", json={"email": email, "role": role}, headers=HEADERS
    )
    assert response.status_code == 201, response.text
    return str(response.json()["user_id"])


def url(org: str, suffix: str = "") -> str:
    return f"/api/organizations/{org}/agents{suffix}"


def create(client: TestClient, org: str, **data: Any) -> Any:
    body = {"name": "Soporte", "base_agent": "research", **data}
    return client.post(url(org), json=body, headers=HEADERS)


def test_owner_manages_lifecycle_with_audit(logged_in: Factory, database: Database) -> None:
    owner = logged_in("owner@example.com", role="admin")
    org = create_org(owner)
    created = create(owner, org, instructions="Cita siempre la política interna.")
    assert created.status_code == 201, created.text
    agent = created.json()
    assert agent["scope"] == "organization" and agent["organization_id"] == org
    assert agent["tools"] == ["documents"] and agent["status"] == "active"

    agent_id = agent["id"]
    edited = owner.patch(url(org, f"/{agent_id}"), json={"name": "Soporte N1"}, headers=HEADERS)
    assert edited.status_code == 200 and edited.json()["name"] == "Soporte N1"
    copy = owner.post(url(org, f"/{agent_id}/duplicate"), headers=HEADERS)
    assert copy.status_code == 201 and copy.json()["status"] == "disabled"
    assert owner.delete(url(org, f"/{agent_id}"), headers=HEADERS).status_code == 204
    assert owner.get(url(org, f"/{agent_id}")).status_code == 404

    actions = audit_actions(database)
    for action in ("create", "update", "duplicate", "delete"):
        assert f"org_agent.{action}" in actions
    with database.connect() as db:
        details = " ".join(r[0] or "" for r in db.execute("SELECT details FROM audit_events"))
    assert "política interna" not in details


def test_roles_admin_manages_member_and_viewer_only_read(logged_in: Factory) -> None:
    owner = logged_in("owner@example.com", role="admin")
    org = create_org(owner)
    admin, member, viewer = (
        logged_in("admin@example.com"),
        logged_in("member@example.com"),
        logged_in("viewer@example.com"),
    )
    add(owner, org, "admin@example.com", "admin")
    add(owner, org, "member@example.com", "member")
    add(owner, org, "viewer@example.com", "viewer")

    assert create(admin, org).status_code == 201
    agent_id = admin.get(url(org)).json()["agents"][0]["id"]
    for client in (member, viewer):
        assert client.get(url(org)).status_code == 200  # agents:read
        assert create(client, org, name="Otro").status_code == 403
        patch = client.patch(url(org, f"/{agent_id}"), json={"name": "x"}, headers=HEADERS)
        assert patch.status_code == 403
        assert client.delete(url(org, f"/{agent_id}"), headers=HEADERS).status_code == 403


def test_outsiders_and_other_organizations_see_nothing(logged_in: Factory) -> None:
    owner = logged_in("owner@example.com", role="admin")
    acme, beta = create_org(owner, "acme"), create_org(owner, "beta")
    agent_id = create(owner, acme).json()["id"]
    outsider = logged_in("outsider@example.com")

    assert outsider.get(url(acme)).status_code == 404  # no se revela que existe
    assert outsider.get(url(acme, f"/{agent_id}")).status_code == 404
    assert owner.get(url(beta, f"/{agent_id}")).status_code == 404  # otra organización
    used = outsider.post("/api/chat", json={"message": "hola", "agent": agent_id}, headers=HEADERS)
    assert used.status_code == 422
    assert agent_id not in [a["id"] for a in outsider.get("/api/agents").json()["agents"]]


def test_member_uses_org_agent_in_chat(
    logged_in: Factory, provider: FakeProvider, database: Database
) -> None:
    owner = logged_in("owner@example.com", role="admin")
    org = create_org(owner)
    member = logged_in("member@example.com")
    add(owner, org, "member@example.com", "member")
    agent_id = create(owner, org, instructions="Firma con «— Acme».").json()["id"]

    listed = {a["id"]: a for a in member.get("/api/agents").json()["agents"]}
    assert listed[agent_id]["scope"] == "organization"
    assert listed[agent_id]["organization_name"] == "Acme"
    assert "instructions" not in listed[agent_id]

    answer = member.post("/api/chat", json={"message": "hola", "agent": agent_id}, headers=HEADERS)
    assert answer.status_code == 200, answer.text
    prompt = provider.requests[-1].messages[0].content
    assert "AGENTE ASISTENTE DE INVESTIGACIÓN" in prompt
    assert "<instrucciones>\nFirma con «— Acme».\n</instrucciones>" in prompt


def test_viewer_cannot_run_and_removed_member_loses_access(logged_in: Factory) -> None:
    owner = logged_in("owner@example.com", role="admin")
    org = create_org(owner)
    viewer, member = logged_in("viewer@example.com"), logged_in("member@example.com")
    add(owner, org, "viewer@example.com", "viewer")
    member_id = add(owner, org, "member@example.com", "member")
    agent_id = create(owner, org).json()["id"]
    body = {"message": "hola", "agent": agent_id}

    assert viewer.post("/api/chat", json=body, headers=HEADERS).status_code == 422  # sin run
    assert member.post("/api/chat", json=body, headers=HEADERS).status_code == 200
    removed = owner.delete(f"/api/organizations/{org}/members/{member_id}", headers=HEADERS)
    assert removed.status_code in (200, 204)
    assert member.post("/api/chat", json=body, headers=HEADERS).status_code == 422


def test_disabled_org_agent_is_not_usable(logged_in: Factory) -> None:
    owner = logged_in("owner@example.com", role="admin")
    org = create_org(owner)
    agent_id = create(owner, org, status="disabled").json()["id"]
    body = {"message": "hola", "agent": agent_id}
    assert owner.post("/api/chat", json=body, headers=HEADERS).status_code == 422
    owner.patch(url(org, f"/{agent_id}"), json={"status": "active"}, headers=HEADERS)
    assert owner.post("/api/chat", json=body, headers=HEADERS).status_code == 200


def test_mutations_need_origin_and_names_are_unique(logged_in: Factory) -> None:
    owner = logged_in("owner@example.com", role="admin")
    org = create_org(owner)
    assert owner.post(url(org), json={"name": "Soporte"}).status_code == 403
    assert create(owner, org).status_code == 201
    assert "ya tiene" in create(owner, org, name="soporte").json()["detail"]
    assert create(owner, org, name="Otro", tools=["shell"]).status_code == 422
