"""Dashboard y avisos: solo datos reales, aislados por usuario y con permisos de administrador."""

from collections.abc import Callable
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from ai_gateway.usage import UsageStore
from nexaro_core.audit import record_event
from nexaro_core.database import Database
from tests.conftest import HEADERS, FakeProvider


def chat(client: TestClient, message: str = "hola") -> str:
    reply = client.post("/api/chat", json={"message": message}, headers=HEADERS)
    assert reply.status_code == 200
    return str(reply.json()["conversation_id"])


def test_dashboard_requires_authentication(client: TestClient) -> None:
    assert client.get("/api/dashboard").status_code == 401
    assert client.get("/api/notifications").status_code == 401


def test_new_user_dashboard_is_all_zeros_not_invented(
    logged_in: Callable[..., TestClient],
) -> None:
    body = logged_in("alice@example.com").get("/api/dashboard").json()

    assert body["activity"]["conversations"] == 0
    assert body["activity"]["messages"] == 0
    assert body["activity"]["last_activity"] is None
    assert body["activity"]["recent"] == []
    assert len(body["activity"]["daily"]) == 14
    assert sum(day["messages"] for day in body["activity"]["daily"]) == 0
    assert body["admin"] is None


def test_activity_counts_only_my_own_data(logged_in: Callable[..., TestClient]) -> None:
    alice = logged_in("alice@example.com")
    bob = logged_in("bob@example.com")
    chat(alice, "uno")
    chat(alice, "dos")
    chat(bob, "secreto de bob")

    activity = alice.get("/api/dashboard").json()["activity"]

    assert activity["conversations"] == 2
    assert activity["messages"] == 4  # 2 turnos x (usuario + asistente)
    today = datetime.now(timezone.utc).date().isoformat()
    assert activity["daily"][-1] == {"date": today, "messages": 4}
    assert activity["last_activity"] is not None
    assert "secreto de bob" not in str(activity)


def test_recent_conversations_are_limited_and_newest_first(
    logged_in: Callable[..., TestClient],
) -> None:
    alice = logged_in("alice@example.com")
    for number in range(7):
        chat(alice, f"tema {number}")

    recent = alice.get("/api/dashboard").json()["activity"]["recent"]

    assert len(recent) == 5
    assert recent[0]["title"] == "tema 6"


def test_days_parameter_is_clamped(logged_in: Callable[..., TestClient]) -> None:
    alice = logged_in("alice@example.com")
    assert len(alice.get("/api/dashboard?days=0").json()["activity"]["daily"]) == 1
    assert len(alice.get("/api/dashboard?days=9999").json()["activity"]["daily"]) == 90


def test_admin_section_only_for_admins(
    logged_in: Callable[..., TestClient], add_user: Callable[..., str]
) -> None:
    user = logged_in("user@example.com")
    admin = logged_in("admin@example.com", role="admin")
    add_user("pending@example.com", approved=False)

    assert user.get("/api/dashboard").json()["admin"] is None
    section = admin.get("/api/dashboard").json()["admin"]

    assert section["users"] == {"total": 3, "pending": 1, "inactive": 0}
    assert section["usage"]["month_cost_usd"] == 0
    assert len(section["usage"]["daily"]) == 14
    assert section["security"] == {"failed_logins_24h": 0, "denied_24h": 0}


def test_admin_usage_reflects_real_model_calls(
    logged_in: Callable[..., TestClient], database: Database
) -> None:
    admin = logged_in("admin@example.com", role="admin")
    store = UsageStore(database)  # el proveedor falso no pasa por el gateway: se registra a mano
    for _ in range(2):
        store.record(user_id=None, provider="ollama", model="m", status="ok", cost_usd=0.0)

    usage = admin.get("/api/dashboard").json()["admin"]["usage"]

    assert usage["requests_period"] == 2
    assert usage["daily"][-1]["requests"] == 2
    assert usage["daily"][-1]["errors"] == 0


def test_security_counters_use_the_audit_log(
    logged_in: Callable[..., TestClient], database: Database, client: TestClient
) -> None:
    admin = logged_in("admin@example.com", role="admin")
    for _ in range(3):
        client.post(
            "/api/auth/login",
            json={"email": "nadie@example.com", "password": "x" * 12},
            headers=HEADERS,
        )
    with database.connect() as db:
        record_event(db, "organization.create", "denied")

    security = admin.get("/api/dashboard").json()["admin"]["security"]

    assert security["failed_logins_24h"] == 3
    assert security["denied_24h"] == 1


def titles(client: TestClient) -> list[str]:
    return [n["title"] for n in client.get("/api/notifications").json()["notifications"]]


def test_no_notifications_when_everything_is_fine(logged_in: Callable[..., TestClient]) -> None:
    body = logged_in("alice@example.com").get("/api/notifications").json()
    assert body["notifications"] == []


def test_model_down_notifies_every_user(
    logged_in: Callable[..., TestClient], provider: FakeProvider
) -> None:
    provider.healthy = False
    alice = logged_in("alice@example.com")
    note = alice.get("/api/notifications").json()["notifications"][0]
    assert note["id"] == "model-unavailable"
    assert note["severity"] == "error"


def test_admin_notifications_are_derived_from_real_state(
    logged_in: Callable[..., TestClient],
    add_user: Callable[..., str],
    client: TestClient,
    database: Database,
) -> None:
    admin = logged_in("admin@example.com", role="admin")
    add_user("pending@example.com", approved=False)
    for _ in range(5):
        client.post(
            "/api/auth/login",
            json={"email": "nadie@example.com", "password": "x" * 12},
            headers=HEADERS,
        )

    notes = {n["id"]: n for n in admin.get("/api/notifications").json()["notifications"]}

    assert notes["pending-approvals"]["href"] == "#/admin"
    assert "1 " in notes["pending-approvals"]["title"]
    assert notes["failed-logins"]["severity"] == "warning"
    assert "registration-open" not in notes  # el registro público nace cerrado


def test_registration_open_is_announced_to_admins_only(
    logged_in: Callable[..., TestClient],
) -> None:
    admin = logged_in("admin@example.com", role="admin")
    user = logged_in("user@example.com")
    admin.patch("/api/admin/settings/registration", json={"enabled": True}, headers=HEADERS)

    assert "registration-open" in [
        n["id"] for n in admin.get("/api/notifications").json()["notifications"]
    ]
    assert user.get("/api/notifications").json()["notifications"] == []


def test_notifications_do_not_leak_emails_or_ips(
    logged_in: Callable[..., TestClient], add_user: Callable[..., str], client: TestClient
) -> None:
    admin = logged_in("admin@example.com", role="admin")
    add_user("pending@example.com", approved=False)
    raw = admin.get("/api/notifications").text
    assert "pending@example.com" not in raw
