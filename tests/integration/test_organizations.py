from collections.abc import Callable

from fastapi.testclient import TestClient

from nexaro_core.database import Database
from tests.conftest import audit_actions

ORIGIN = {"Origin": "http://127.0.0.1:8001"}
Factory = Callable[..., TestClient]


def create_org(admin: TestClient, slug: str = "acme") -> str:
    response = admin.post("/api/organizations", json={"name": "Acme", "slug": slug}, headers=ORIGIN)
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


def test_only_platform_admins_create_organizations(logged_in: Factory) -> None:
    user = logged_in("user@example.com")
    body = {"name": "X", "slug": "xx"}
    assert user.post("/api/organizations", json=body, headers=ORIGIN).status_code == 403
    assert user.post("/api/organizations", json=body).status_code in (401, 403)


def test_creator_becomes_owner_with_a_free_subscription(
    logged_in: Factory, database: Database
) -> None:
    admin = logged_in("admin@example.com", role="admin")
    org = create_org(admin)

    [mine] = admin.get("/api/organizations").json()["organizations"]
    assert (mine["id"], mine["role"]) == (org, "owner")
    with database.connect() as db:
        plan = db.execute(
            "SELECT plan, status FROM subscriptions WHERE organization_id = ?", (org,)
        )
        assert tuple(plan.fetchone()) == ("free", "active")


def test_slug_validation_and_uniqueness(logged_in: Factory) -> None:
    admin = logged_in("admin@example.com", role="admin")
    create_org(admin, "acme")
    dup = admin.post("/api/organizations", json={"name": "Otra", "slug": "acme"}, headers=ORIGIN)
    assert dup.status_code == 409
    bad = admin.post(
        "/api/organizations", json={"name": "Otra", "slug": "Mal Slug!"}, headers=ORIGIN
    )
    assert bad.status_code == 400


def test_non_members_get_404_even_platform_admins(logged_in: Factory) -> None:
    owner = logged_in("owner@example.com", role="admin")
    org = create_org(owner)
    outsider = logged_in("outsider@example.com")
    other_admin = logged_in("other-admin@example.com", role="admin")

    for client in (outsider, other_admin):
        assert client.get(f"/api/organizations/{org}/members").status_code == 404
        assert client.get("/api/organizations").json() == {"organizations": []}
    # Un id inexistente responde igual que uno ajeno: no se revela qué existe.
    assert outsider.get("/api/organizations/no-existe/members").status_code == 404


def test_member_management_and_permissions(logged_in: Factory, database: Database) -> None:
    owner = logged_in("owner@example.com", role="admin")
    org = create_org(owner)
    viewer = logged_in("viewer@example.com")
    logged_in("member@example.com")

    added = owner.post(
        f"/api/organizations/{org}/members",
        json={"email": "viewer@example.com", "role": "viewer"},
        headers=ORIGIN,
    )
    assert added.status_code == 201

    assert viewer.get(f"/api/organizations/{org}/members").status_code == 200  # members:read
    denied = viewer.post(
        f"/api/organizations/{org}/members",
        json={"email": "member@example.com", "role": "member"},
        headers=ORIGIN,
    )
    assert denied.status_code == 403
    assert "authz.permission_denied" in audit_actions(database)  # la denegación quedó auditada

    unknown = owner.post(
        f"/api/organizations/{org}/members",
        json={"email": "nadie@example.com", "role": "member"},
        headers=ORIGIN,
    )
    assert unknown.status_code == 404
    assert (
        owner.post(
            f"/api/organizations/{org}/members",
            json={"email": "viewer@example.com", "role": "member"},
            headers=ORIGIN,
        ).status_code
        == 409
    )
    assert (
        owner.post(
            f"/api/organizations/{org}/members",
            json={"email": "member@example.com", "role": "superuser"},
            headers=ORIGIN,
        ).status_code
        == 400
    )


def test_admin_cannot_touch_owners_and_last_owner_is_protected(
    logged_in: Factory, add_user: Callable[..., str]
) -> None:
    owner = logged_in("owner@example.com", role="admin")
    org = create_org(owner)
    member_admin = logged_in("ma@example.com")
    add_user_id = owner.get("/api/auth/me").json()["user"]["id"]
    owner.post(
        f"/api/organizations/{org}/members",
        json={"email": "ma@example.com", "role": "admin"},
        headers=ORIGIN,
    )

    # Un admin de la organización no puede nombrar ni degradar propietarios.
    assert (
        member_admin.post(
            f"/api/organizations/{org}/members",
            json={"email": "owner@example.com", "role": "owner"},
            headers=ORIGIN,
        ).status_code
        == 403
    )
    assert (
        member_admin.patch(
            f"/api/organizations/{org}/members/{add_user_id}",
            json={"role": "viewer"},
            headers=ORIGIN,
        ).status_code
        == 403
    )
    assert (
        member_admin.delete(
            f"/api/organizations/{org}/members/{add_user_id}", headers=ORIGIN
        ).status_code
        == 403
    )

    # El último propietario no puede degradarse ni irse.
    assert (
        owner.patch(
            f"/api/organizations/{org}/members/{add_user_id}",
            json={"role": "admin"},
            headers=ORIGIN,
        ).status_code
        == 400
    )
    assert (
        owner.delete(f"/api/organizations/{org}/members/{add_user_id}", headers=ORIGIN).status_code
        == 400
    )


def test_removed_member_loses_access_and_mutations_need_origin(logged_in: Factory) -> None:
    owner = logged_in("owner@example.com", role="admin")
    org = create_org(owner)
    member = logged_in("m@example.com")
    owner.post(
        f"/api/organizations/{org}/members",
        json={"email": "m@example.com", "role": "member"},
        headers=ORIGIN,
    )
    user_id = member.get("/api/auth/me").json()["user"]["id"]
    assert member.get(f"/api/organizations/{org}/members").status_code == 200

    assert (
        owner.delete(f"/api/organizations/{org}/members/{user_id}").status_code == 403
    )  # sin Origin
    assert (
        owner.delete(f"/api/organizations/{org}/members/{user_id}", headers=ORIGIN).status_code
        == 200
    )
    assert member.get(f"/api/organizations/{org}/members").status_code == 404


def test_suspended_organization_denies_access(logged_in: Factory, database: Database) -> None:
    owner = logged_in("owner@example.com", role="admin")
    org = create_org(owner)
    with database.connect() as db:
        db.execute("UPDATE organizations SET status = 'suspended' WHERE id = ?", (org,))
    assert owner.get(f"/api/organizations/{org}/members").status_code == 404
    assert owner.get("/api/organizations").json() == {"organizations": []}
