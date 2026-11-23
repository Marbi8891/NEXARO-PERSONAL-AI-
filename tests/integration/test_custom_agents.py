"""Persistencia y autorización del registro de agentes personalizados."""
from collections.abc import Callable

from fastapi.testclient import TestClient

from nexaro_core.database import Database
from tests.conftest import HEADERS
from tests.integration.test_chat_documents import setup_org

Factory = Callable[..., TestClient]

BODY = {
    "name": "Agente de planificación",
    "description": "Descompone objetivos en tareas claras y priorizadas.",
    "system_prompt": "Eres un agente de planificación. Propón pasos concretos y valida supuestos.",
    "category": "productivity",
    "model": "qwen2.5:3b",
    "tools": [],
    "permissions": {"filesystem": "none", "terminal": False, "network": False},
    "memory": {"enabled": False, "scope": "none"},
    "autonomy": "assisted",
}


def test_custom_agent_crud_and_tenant_isolation(logged_in: Factory) -> None:
    admin, org_id = setup_org(logged_in)
    base = f"/api/organizations/{org_id}/agents"
    created = admin.post(base, json=BODY, headers=HEADERS)
    assert created.status_code == 201, created.text
    agent = created.json()
    assert agent["name"] == BODY["name"]
    assert agent["system_prompt"] == BODY["system_prompt"]
    assert agent["tools"] == [] and agent["permissions"] == BODY["permissions"]
    assert agent["autonomy"] == "assisted"
    assert admin.get(base).json()["agents"][0]["id"] == agent["id"]
    assert admin.get(f"{base}/{agent['id']}").status_code == 200

    updated = {**BODY, "name": "Planificador actualizado", "status": "disabled"}
    put = admin.put(f"{base}/{agent['id']}", json=updated, headers=HEADERS)
    assert put.status_code == 200, put.text
    assert put.json()["status"] == "disabled"
    assert put.json()["name"] == updated["name"]
    assert admin.delete(f"{base}/{agent['id']}", headers=HEADERS).status_code == 204
    assert admin.get(f"{base}/{agent['id']}").status_code == 404


def test_custom_agent_rejects_unsafe_capabilities(logged_in: Factory) -> None:
    admin, org_id = setup_org(logged_in)
    base = f"/api/organizations/{org_id}/agents"
    unsafe = {**BODY, "tools": ["terminal"], "permissions": {"filesystem": "read_only", "terminal": True, "network": False}}
    response = admin.post(base, json=unsafe, headers=HEADERS)
    assert response.status_code == 422
    assert "herramientas ejecutables" in response.json()["detail"]


def test_custom_agents_require_org_permissions(logged_in: Factory) -> None:
    _, org_id = setup_org(logged_in)
    outsider = logged_in("outsider@example.com")
    base = f"/api/organizations/{org_id}/agents"
    assert outsider.get(base).status_code == 404
    assert outsider.post(base, json=BODY, headers=HEADERS).status_code == 404


def test_agent_configuration_json_is_persisted(logged_in: Factory, database: Database) -> None:
    admin, org_id = setup_org(logged_in)
    response = admin.post(f"/api/organizations/{org_id}/agents", json=BODY, headers=HEADERS)
    assert response.status_code == 201
    with database.connect() as db:
        row = db.execute("SELECT tools_json, permissions_json, memory_json FROM agents WHERE id = ?", (response.json()["id"],)).fetchone()
    import json
    assert json.loads(row["tools_json"]) == []
    assert json.loads(row["permissions_json"]) == BODY["permissions"]
    assert json.loads(row["memory_json"]) == BODY["memory"]
