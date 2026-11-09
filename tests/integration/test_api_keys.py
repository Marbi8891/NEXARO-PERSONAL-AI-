"""Claves de API: gestión por organización, autenticación Bearer, revocación y uso."""

from collections.abc import Callable

from fastapi.testclient import TestClient

from ai_gateway.usage import UsageStore
from nexaro_core.database import Database
from tests.conftest import ORIGIN, FakeProvider, audit_actions

HEADERS = {"Origin": ORIGIN}
Factory = Callable[..., TestClient]


def setup_org(logged_in: Factory) -> tuple[TestClient, str]:
    admin = logged_in("owner@example.com", role="admin")
    org = admin.post("/api/organizations", json={"name": "Acme", "slug": "acme"}, headers=HEADERS)
    return admin, str(org.json()["id"])


def make_key(admin: TestClient, org: str, name: str = "CI", **extra: object) -> dict:
    response = admin.post(
        f"/api/organizations/{org}/api-keys", json={"name": name, **extra}, headers=HEADERS
    )
    assert response.status_code == 201, response.text
    return dict(response.json())


def bearer(secret: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {secret}"}


def call(client: TestClient, secret: str, message: str = "hola") -> object:
    return client.post("/api/v1/chat", json={"message": message}, headers=bearer(secret))


def test_secret_is_shown_once_and_only_its_hash_is_stored(
    logged_in: Factory, database: Database
) -> None:
    admin, org = setup_org(logged_in)
    created = make_key(admin, org)

    assert created["secret"].startswith("nxr_") and len(created["secret"]) > 40
    listed = admin.get(f"/api/organizations/{org}/api-keys").json()["api_keys"]
    assert [k["name"] for k in listed] == ["CI"]
    assert created["secret"] not in str(listed)
    assert "key_hash" not in listed[0] and "secret" not in listed[0]
    assert listed[0]["prefix"] == created["secret"][: len(listed[0]["prefix"])]
    assert listed[0]["status"] == "active"
    with database.connect() as db:
        dump = " ".join(str(tuple(r)) for r in db.execute("SELECT * FROM api_keys"))
        audit = " ".join(str(tuple(r)) for r in db.execute("SELECT * FROM audit_events"))
    assert created["secret"] not in dump and created["secret"] not in audit


def test_only_owner_and_admin_roles_manage_keys(logged_in: Factory, add_user: Callable) -> None:
    admin, org = setup_org(logged_in)
    for email, role in (("m@example.com", "member"), ("v@example.com", "viewer")):
        add_user(email)
        admin.post(
            f"/api/organizations/{org}/members",
            json={"email": email, "role": role},
            headers=HEADERS,
        )
    outsider = logged_in("out@example.com")
    member = TestClient(admin.app)
    assert (
        member.post(
            "/api/auth/login",
            json={"email": "m@example.com", "password": "correct-horse-battery"},
            headers=HEADERS,
        ).status_code
        == 200
    )

    path = f"/api/organizations/{org}/api-keys"
    assert member.get(path).status_code == 403
    assert member.post(path, json={"name": "x"}, headers=HEADERS).status_code == 403
    assert outsider.get(path).status_code == 404  # no revela que existe
    assert outsider.post(path, json={"name": "x"}, headers=HEADERS).status_code == 404


def test_create_requires_origin_and_valid_name(logged_in: Factory) -> None:
    admin, org = setup_org(logged_in)
    path = f"/api/organizations/{org}/api-keys"
    assert admin.post(path, json={"name": "x"}).status_code == 403
    assert admin.post(path, json={"name": ""}, headers=HEADERS).status_code == 422
    assert (
        admin.post(path, json={"name": "x", "expires_in_days": 0}, headers=HEADERS).status_code
        == 422
    )


def test_bearer_key_chats_without_cookie_or_origin(
    logged_in: Factory, app: object, provider: FakeProvider, database: Database
) -> None:
    admin, org = setup_org(logged_in)
    secret = make_key(admin, org)["secret"]
    anonymous = TestClient(app)  # sin cookies, sin Origin

    response = call(anonymous, secret)

    assert response.status_code == 200, response.text
    assert response.json()["answer"] == "respuesta de prueba"
    sent = provider.requests[-1]
    assert sent.organization_id == org and sent.api_key_id is not None
    [key] = admin.get(f"/api/organizations/{org}/api-keys").json()["api_keys"]
    assert key["last_used_at"] is not None


def test_invalid_keys_are_rejected_without_saying_why(logged_in: Factory, app: object) -> None:
    admin, org = setup_org(logged_in)
    created = make_key(admin, org)
    admin.delete(f"/api/organizations/{org}/api-keys/{created['id']}", headers=HEADERS)
    anonymous = TestClient(app)

    bodies = set()
    for headers in (
        {},
        {"Authorization": "Bearer nxr_inventada"},
        {"Authorization": "Bearer no-es-nuestra"},
        {"Authorization": "Basic abc"},
        bearer(created["secret"]),  # revocada
    ):
        response = anonymous.post("/api/v1/chat", json={"message": "hola"}, headers=headers)
        assert response.status_code == 401
        assert response.headers["www-authenticate"] == "Bearer"
        bodies.add(response.text)
    assert len(bodies) == 1


def test_a_session_cookie_does_not_authenticate_the_public_api(logged_in: Factory) -> None:
    admin, _ = setup_org(logged_in)
    assert admin.post("/api/v1/chat", json={"message": "hola"}).status_code == 401


def test_revocation_is_audited_idempotent_and_scoped_to_the_organization(
    logged_in: Factory, database: Database
) -> None:
    admin, org = setup_org(logged_in)
    other = admin.post("/api/organizations", json={"name": "Otra", "slug": "otra"}, headers=HEADERS)
    other_org = other.json()["id"]
    key = make_key(admin, org)

    wrong_org = admin.delete(
        f"/api/organizations/{other_org}/api-keys/{key['id']}", headers=HEADERS
    )
    assert wrong_org.status_code == 404
    assert (
        admin.delete(f"/api/organizations/{org}/api-keys/{key['id']}", headers=HEADERS).status_code
        == 204
    )
    first = admin.get(f"/api/organizations/{org}/api-keys").json()["api_keys"][0]["revoked_at"]
    assert (
        admin.delete(f"/api/organizations/{org}/api-keys/{key['id']}", headers=HEADERS).status_code
        == 204
    )
    again = admin.get(f"/api/organizations/{org}/api-keys").json()["api_keys"][0]
    assert again["revoked_at"] == first and again["status"] == "revoked"
    assert (
        admin.delete(f"/api/organizations/{org}/api-keys/{key['id']}").status_code == 403
    )  # sin Origin
    actions = audit_actions(database)
    assert "apikey.create" in actions and actions.count("apikey.revoke") == 2


def test_expired_key_stops_working(logged_in: Factory, app: object, database: Database) -> None:
    admin, org = setup_org(logged_in)
    created = make_key(admin, org, expires_in_days=7)
    anonymous = TestClient(app)
    assert call(anonymous, created["secret"]).status_code == 200

    with database.connect() as db:
        db.execute("UPDATE api_keys SET expires_at = '2000-01-01 00:00:00'")

    assert call(anonymous, created["secret"]).status_code == 401
    listed = admin.get(f"/api/organizations/{org}/api-keys").json()["api_keys"]
    assert listed[0]["status"] == "expired"


def test_key_dies_with_its_creator_membership_or_account(
    logged_in: Factory, app: object, database: Database
) -> None:
    admin, org = setup_org(logged_in)
    secret = make_key(admin, org)["secret"]
    anonymous = TestClient(app)
    assert call(anonymous, secret).status_code == 200

    with database.connect() as db:
        db.execute("UPDATE memberships SET status = 'suspended'")
    assert call(anonymous, secret).status_code == 401
    with database.connect() as db:
        db.execute("UPDATE memberships SET status = 'active'")
    assert call(anonymous, secret).status_code == 200
    with database.connect() as db:
        db.execute("UPDATE users SET is_active = 0")
    assert call(anonymous, secret).status_code == 401
    with database.connect() as db:
        db.execute("UPDATE users SET is_active = 1")
        db.execute("UPDATE organizations SET status = 'suspended'")
    assert call(anonymous, secret).status_code == 401


def test_repeated_failures_from_one_ip_are_rate_limited(client: TestClient) -> None:
    codes = [call(client, "nxr_mala").status_code for _ in range(30)]
    assert codes[0] == 401 and 429 in codes


def test_key_limit_per_organization(logged_in: Factory) -> None:
    admin, org = setup_org(logged_in)
    for number in range(25):
        make_key(admin, org, name=f"k{number}")
    extra = admin.post(f"/api/organizations/{org}/api-keys", json={"name": "k26"}, headers=HEADERS)
    assert extra.status_code == 409


def test_usage_is_per_key_and_only_counts_real_records(
    logged_in: Factory, database: Database
) -> None:
    admin, org = setup_org(logged_in)
    empty = admin.get(f"/api/organizations/{org}/usage").json()
    assert empty == {"days": 30, "keys": []}

    key = make_key(admin, org, "Produccion")
    store = UsageStore(database)
    for status in ("ok", "ok", "error"):
        store.record(
            user_id=None, provider="p", model="m", status=status, input_tokens=10,
            output_tokens=5, cost_usd=0.25, organization_id=org, api_key_id=key["id"],
        )  # fmt: skip
    store.record(user_id=None, provider="p", model="m", status="ok")  # sin organización: no cuenta

    [row] = admin.get(f"/api/organizations/{org}/usage?days=500").json()["keys"]
    assert (row["name"], row["requests"], row["errors"]) == ("Produccion", 3, 1)
    assert (row["input_tokens"], row["output_tokens"]) == (30, 15)
    assert row["cost_usd"] == 0.75
    assert admin.get(f"/api/organizations/{org}/usage?days=500").json()["days"] == 90


def test_usage_is_isolated_between_organizations(logged_in: Factory, database: Database) -> None:
    admin, org = setup_org(logged_in)
    other = admin.post("/api/organizations", json={"name": "O", "slug": "oo"}, headers=HEADERS)
    other_org = other.json()["id"]
    key = make_key(admin, other_org)
    UsageStore(database).record(
        user_id=None, provider="p", model="m", status="ok",
        organization_id=other_org, api_key_id=key["id"],
    )  # fmt: skip
    assert admin.get(f"/api/organizations/{org}/usage").json()["keys"] == []


def test_usage_cannot_reference_a_key_of_another_organization(
    logged_in: Factory, database: Database
) -> None:
    admin, org = setup_org(logged_in)
    other = admin.post("/api/organizations", json={"name": "O", "slug": "oo"}, headers=HEADERS)
    key = make_key(admin, org)
    store = UsageStore(database)

    for wrong_org in (other.json()["id"], None):
        try:
            store.record(
                user_id=None, provider="p", model="m", status="ok",
                organization_id=wrong_org, api_key_id=key["id"],
            )  # fmt: skip
        except Exception as exc:  # sqlite3.IntegrityError por el trigger
            assert "api_key_id" in str(exc)
        else:
            raise AssertionError("se aceptó una clave de otra organización")
