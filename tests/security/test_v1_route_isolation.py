"""Aislamiento de las rutas que trae la integración v1.0 (PRs #8-#11) y que el inventario de
`test_12e_no_route_exposes_agents_tasks_or_embeddings_without_a_scoped_test` exige probar.

Completa los tests de cada PR: alguien de fuera de la organización, o la misma persona desde OTRA
organización, no puede leer, crear, cambiar, duplicar, borrar, instalar ni restaurar nada. La
respuesta es siempre 404 (no se revela que el recurso existe) y el recurso sigue intacto.
"""

from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient

from tests.conftest import HEADERS

pytestmark = pytest.mark.security
Factory = Callable[..., TestClient]


def _org(owner: TestClient, slug: str) -> str:
    response = owner.post(
        "/api/organizations", json={"name": slug.title(), "slug": slug}, headers=HEADERS
    )
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


def test_organization_agents_cannot_be_touched_from_outside(logged_in: Factory) -> None:
    owner = logged_in("owner@example.com", role="admin")
    acme, beta = _org(owner, "acme"), _org(owner, "beta")
    created = owner.post(
        f"/api/organizations/{acme}/agents",
        json={"name": "Soporte", "base_agent": "research"},
        headers=HEADERS,
    )
    assert created.status_code == 201, created.text
    agent_id = created.json()["id"]
    outsider = logged_in("outsider@example.com")

    for client, org in ((outsider, acme), (owner, beta)):  # fuera, y desde otra organización
        base = f"/api/organizations/{org}/agents"
        item = f"{base}/{agent_id}"
        assert client.get(item).status_code == 404
        assert client.patch(item, json={"name": "robado"}, headers=HEADERS).status_code == 404
        assert client.post(f"{item}/duplicate", headers=HEADERS).status_code == 404
        assert client.delete(item, headers=HEADERS).status_code == 404
    base = f"/api/organizations/{acme}/agents"
    assert outsider.get(base).status_code == 404
    assert (
        outsider.post(
            base, json={"name": "intruso", "base_agent": "general"}, headers=HEADERS
        ).status_code
        == 404
    )
    assert owner.get(f"{base}/{agent_id}").json()["name"] == "Soporte"  # intacto


def test_prompts_cannot_be_touched_from_outside(logged_in: Factory) -> None:
    owner = logged_in("owner@example.com", role="admin")
    acme, beta = _org(owner, "acme"), _org(owner, "beta")
    body = {"name": "Revisión", "category": "Software", "user_template": "Revisa el código"}
    created = owner.post(f"/api/organizations/{acme}/prompts", json=body, headers=HEADERS)
    assert created.status_code == 201, created.text
    prompt_id = created.json()["id"]
    outsider = logged_in("outsider@example.com")

    for client, org in ((outsider, acme), (owner, beta)):
        item = f"/api/organizations/{org}/prompts/{prompt_id}"
        assert client.get(item).status_code == 404
        assert client.get(f"{item}/versions").status_code == 404
        assert client.patch(item, json={"name": "robado"}, headers=HEADERS).status_code == 404
        assert (
            client.post(f"{item}/render", json={"values": {}}, headers=HEADERS).status_code == 404
        )
        assert client.post(f"{item}/versions/1/restore", headers=HEADERS).status_code == 404
        assert client.delete(item, headers=HEADERS).status_code == 404
    base = f"/api/organizations/{acme}/prompts"
    assert outsider.get(base).status_code == 404
    assert outsider.post(base, json=body, headers=HEADERS).status_code == 404
    assert (
        outsider.post(f"{base}/install", json={"catalogue_id": "x"}, headers=HEADERS).status_code
        == 404
    )
    assert owner.get(f"{base}/{prompt_id}").json()["name"] == "Revisión"


def test_custom_agents_are_private_to_their_owner(logged_in: Factory) -> None:
    alice = logged_in("alice@example.com")
    bob = logged_in("bob@example.com")
    created = alice.post(
        "/api/agents/custom", json={"name": "Privado", "base_agent": "general"}, headers=HEADERS
    )
    assert created.status_code == 201, created.text
    item = f"/api/agents/custom/{created.json()['id']}"
    assert bob.get(item).status_code == 404
    assert bob.patch(item, json={"name": "mío"}, headers=HEADERS).status_code == 404
    assert bob.post(f"{item}/duplicate", headers=HEADERS).status_code == 404
    assert bob.delete(item, headers=HEADERS).status_code == 404
    assert alice.get(item).json()["name"] == "Privado"
