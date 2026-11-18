"""Agentes especializados (ADR-0022): registro, prompts, herramientas con permiso y auditoría."""

import json
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient

from nexaro_core.config import Settings
from nexaro_core.database import Database
from products.personal_ai.agents import AGENTS, TOOL_PERMISSIONS
from products.personal_ai.guard import REFUSAL
from products.personal_ai.prompts import SYSTEM_PROMPT, TUTOR_RULES, build_system_prompt
from tests.conftest import HEADERS, FakeProvider
from tests.integration.test_api_keys import bearer, make_key
from tests.integration.test_chat_documents import setup_org, upload

Factory = Callable[..., TestClient]
CODE_QUESTION = "Escribe una función en Python que invierta una lista"
REQUIRED = ["general", "developer", "security", "research", "productivity", "data"]


def agent_events(database: Database) -> list[dict[str, Any]]:
    with database.connect() as db:
        rows = db.execute(
            "SELECT outcome, actor_user_id, target_id, details FROM audit_events"
            " WHERE action = 'agent.tool' ORDER BY id"
        ).fetchall()
    return [{**dict(r), "details": json.loads(r["details"])} for r in rows]


def test_registry_has_the_required_agents_and_keeps_the_tutor() -> None:
    assert [a for a in AGENTS if a != "tutor"] == REQUIRED
    assert len({a.name for a in AGENTS.values()}) == len(AGENTS)
    assert all(tool in TOOL_PERMISSIONS for a in AGENTS.values() for tool in a.tools)
    assert AGENTS["tutor"].tools == frozenset()  # mínimo privilegio: no lee documentos


@pytest.mark.parametrize("agent", list(AGENTS))
def test_every_agent_extends_the_general_prompt(agent: str) -> None:
    """Identidad, seguridad y confidencialidad (ADR-0019) son las mismas para todos."""
    prompt = build_system_prompt(agent)
    assert prompt.startswith(SYSTEM_PROMPT)
    assert REFUSAL in prompt
    assert (prompt == SYSTEM_PROMPT) == (agent == "general")


def test_agents_endpoint_requires_a_session(client: TestClient, logged_in: Factory) -> None:
    assert client.get("/api/agents").status_code == 401
    body = logged_in("alice@example.com").get("/api/agents").json()
    assert [a["id"] for a in body["agents"]] == list(AGENTS)
    tutor = next(a for a in body["agents"] if a["id"] == "tutor")
    assert tutor["tools"] == [] and tutor["name"] == "Tutor de programación"
    assert "rules" not in tutor and "prompt" not in json.dumps(body)  # el prompt no se publica


@pytest.mark.parametrize("agent", list(AGENTS))
def test_chat_uses_the_selected_agent(
    agent: str, logged_in: Factory, provider: FakeProvider
) -> None:
    alice = logged_in("alice@example.com")
    response = alice.post("/api/chat", json={"message": "hola", "agent": agent}, headers=HEADERS)
    assert response.status_code == 200, response.text
    assert response.json()["agent"] == agent
    assert provider.requests[-1].messages[0].content == build_system_prompt(agent)


def test_agent_wins_over_the_legacy_mode(logged_in: Factory, provider: FakeProvider) -> None:
    alice = logged_in("alice@example.com")
    body = {"message": "hola", "agent": "security", "mode": "tutor"}
    assert alice.post("/api/chat", json=body, headers=HEADERS).json()["agent"] == "security"
    assert provider.requests[-1].messages[0].content == build_system_prompt("security")
    # Sin agente, el modo heredado sigue eligiendo el tutor (ADR-0020).
    alice.post("/api/chat", json={"message": "hola", "mode": "tutor"}, headers=HEADERS)
    assert provider.requests[-1].messages[0].content.endswith(TUTOR_RULES)


def test_unknown_agent_is_rejected(logged_in: Factory, provider: FakeProvider) -> None:
    alice = logged_in("alice@example.com")
    body = {"message": "hola", "agent": "root"}
    assert alice.post("/api/chat", json=body, headers=HEADERS).status_code == 422
    assert provider.requests == []


@pytest.mark.parametrize(
    ("agent", "budget"),
    [("developer", "code"), ("data", "code"), ("research", "default"), ("tutor", "default")],
)
def test_long_code_answers_depend_on_the_agent(
    agent: str, budget: str, logged_in: Factory, provider: FakeProvider, settings: Settings
) -> None:
    limits = {"code": settings.output_tokens_code, "default": settings.output_tokens_default}
    alice = logged_in("alice@example.com")
    alice.post("/api/chat", json={"message": CODE_QUESTION, "agent": agent}, headers=HEADERS)
    assert provider.requests[-1].max_output_tokens == limits[budget]


def test_each_answer_records_which_agent_gave_it(
    logged_in: Factory, provider: FakeProvider
) -> None:
    alice = logged_in("alice@example.com")
    first = alice.post("/api/chat", json={"message": "hola", "agent": "research"}, headers=HEADERS)
    conv = first.json()["conversation_id"]
    alice.post(
        "/api/chat",
        json={"message": "¿qué modelo de IA eres?", "agent": "data", "conversation_id": conv},
        headers=HEADERS,
    )
    messages = alice.get(f"/api/conversations/{conv}").json()["messages"]
    assert [(m["role"], m["agent"]) for m in messages] == [
        ("user", None),
        ("assistant", "research"),
        ("user", None),
        ("assistant", "data"),  # también la respuesta fija del filtro de temas internos
    ]


def test_streaming_announces_the_agent(logged_in: Factory, provider: FakeProvider) -> None:
    alice = logged_in("alice@example.com")
    response = alice.post(
        "/api/chat/stream", json={"message": "hola", "agent": "productivity"}, headers=HEADERS
    )
    start = json.loads(response.text.split("\n\n")[0][6:])
    assert start["event"] == "start" and start["agent"] == "productivity"
    assert provider.requests[-1].messages[0].content == build_system_prompt("productivity")


def test_agent_without_the_tool_cannot_read_documents(
    logged_in: Factory, provider: FakeProvider, database: Database
) -> None:
    admin, org = setup_org(logged_in)
    upload(admin, org, "Contrato", "La fianza equivale a dos mensualidades.")
    body = {"message": "¿Cuánto es la fianza?", "agent": "tutor", "document_organization_id": org}
    for path in ("/api/chat", "/api/chat/stream"):
        response = admin.post(path, json=body, headers=HEADERS)
        assert response.status_code == 403
        assert response.json() == {"detail": "Este agente no puede consultar documentos"}
    assert provider.requests == []  # ni se consulta al modelo ni se guarda el turno
    with database.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM messages").fetchone()[0] == 0
    events = agent_events(database)
    assert [e["outcome"] for e in events] == ["denied", "denied"]
    assert events[0]["details"] == {
        "agent": "tutor",
        "tool": "documents",
        "reason": "agent_without_tool",
    }
    assert events[0]["target_id"] == org


def test_tool_use_is_audited_without_content(
    logged_in: Factory, provider: FakeProvider, database: Database
) -> None:
    admin, org = setup_org(logged_in)
    upload(admin, org, "Contrato", "La fianza equivale a dos mensualidades.")
    body = {"message": "¿Fianza?", "agent": "research", "document_organization_id": org}
    response = admin.post("/api/chat", json=body, headers=HEADERS)
    assert response.status_code == 200 and response.json()["sources"]
    admin.post("/api/chat/stream", json=body, headers=HEADERS)

    events = agent_events(database)
    assert [e["outcome"] for e in events] == ["success", "success"]
    assert events[0]["details"] == {"agent": "research", "tool": "documents", "sources": 1}
    assert events[1]["details"] == {"agent": "research", "tool": "documents"}
    raw = json.dumps(events)
    assert "fianza" not in raw and "mensualidades" not in raw


def test_user_permission_is_still_required_with_the_tool(
    logged_in: Factory, provider: FakeProvider
) -> None:
    _, org = setup_org(logged_in)
    outsider = logged_in("outsider@example.com")
    body = {"message": "hola", "agent": "research", "document_organization_id": org}
    assert outsider.post("/api/chat", json=body, headers=HEADERS).status_code in {403, 404}
    assert provider.requests == []


def test_agents_through_an_api_key(
    client: TestClient, logged_in: Factory, provider: FakeProvider
) -> None:
    admin, org = setup_org(logged_in)
    key = make_key(admin, org)
    response = client.post(
        "/api/v1/chat",
        json={"message": "revisa este código", "agent": "developer"},
        headers=bearer(key["secret"]),
    )
    assert response.status_code == 200, response.text
    assert response.json()["agent"] == "developer"
    assert provider.requests[-1].messages[0].content == build_system_prompt("developer")
