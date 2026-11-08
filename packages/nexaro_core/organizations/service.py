"""Organizaciones, membresías y permisos. El acceso a datos de una organización pasa siempre por
`get_membership`/`has_permission`: quien no es miembro activo no obtiene nada."""

import re
import sqlite3
import uuid
from dataclasses import dataclass
from typing import Any

SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,62}$")
ROLES = ("owner", "admin", "member", "viewer")


class OrganizationError(Exception):
    """Error de negocio con mensaje seguro para el cliente."""


class SlugTakenError(OrganizationError):
    pass


class UserNotFoundError(OrganizationError):
    pass


class AlreadyMemberError(OrganizationError):
    pass


class MemberNotFoundError(OrganizationError):
    pass


class LastOwnerError(OrganizationError):
    pass


class RoleChangeNotAllowedError(OrganizationError):
    pass


@dataclass(frozen=True)
class Membership:
    organization_id: str
    user_id: str
    role: str


def create_organization(
    db: sqlite3.Connection, name: str, slug: str, created_by: str
) -> dict[str, Any]:
    """Crea la organización, la hace propietaria al creador y le da una suscripción gratuita."""
    name = name.strip()
    if not name or len(name) > 120:
        raise OrganizationError("El nombre debe tener entre 1 y 120 caracteres")
    if not SLUG_RE.fullmatch(slug):
        raise OrganizationError("El identificador admite minúsculas, números y guiones (2-63)")

    organization_id = str(uuid.uuid4())
    try:
        db.execute(
            "INSERT INTO organizations (id, name, slug, created_by) VALUES (?, ?, ?, ?)",
            (organization_id, name, slug, created_by),
        )
    except sqlite3.IntegrityError as exc:
        raise SlugTakenError("Ya existe una organización con ese identificador") from exc

    db.execute(
        "INSERT INTO memberships (id, organization_id, user_id, role_id) VALUES (?, ?, ?, 'owner')",
        (str(uuid.uuid4()), organization_id, created_by),
    )
    db.execute(
        "INSERT INTO subscriptions (id, organization_id) VALUES (?, ?)",
        (str(uuid.uuid4()), organization_id),
    )
    return {"id": organization_id, "name": name, "slug": slug, "status": "active"}


def get_membership(db: sqlite3.Connection, user_id: str, organization_id: str) -> Membership | None:
    """Membresía activa en una organización activa; None en cualquier otro caso."""
    row = db.execute(
        """
        SELECT m.role_id FROM memberships m
        JOIN organizations o ON o.id = m.organization_id
        WHERE m.user_id = ? AND m.organization_id = ?
          AND m.status = 'active' AND o.status = 'active'
        """,
        (user_id, organization_id),
    ).fetchone()
    return Membership(organization_id, user_id, row["role_id"]) if row else None


def has_permission(db: sqlite3.Connection, membership: Membership, permission: str) -> bool:
    row = db.execute(
        "SELECT 1 FROM role_permissions WHERE role_id = ? AND permission_id = ?",
        (membership.role, permission),
    ).fetchone()
    return row is not None


def list_user_organizations(db: sqlite3.Connection, user_id: str) -> list[dict[str, Any]]:
    rows = db.execute(
        """
        SELECT o.id, o.name, o.slug, m.role_id AS role
        FROM memberships m JOIN organizations o ON o.id = m.organization_id
        WHERE m.user_id = ? AND m.status = 'active' AND o.status = 'active'
        ORDER BY o.name
        """,
        (user_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def list_members(db: sqlite3.Connection, organization_id: str) -> list[dict[str, Any]]:
    rows = db.execute(
        """
        SELECT u.id AS user_id, u.email, m.role_id AS role, m.status
        FROM memberships m JOIN users u ON u.id = m.user_id
        WHERE m.organization_id = ? ORDER BY u.email
        """,
        (organization_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def _check_role(role: str) -> None:
    if role not in ROLES:
        raise OrganizationError("Rol no válido")


def _current_role(db: sqlite3.Connection, organization_id: str, user_id: str) -> str:
    row = db.execute(
        "SELECT role_id FROM memberships WHERE organization_id = ? AND user_id = ?",
        (organization_id, user_id),
    ).fetchone()
    if row is None:
        raise MemberNotFoundError("Miembro no encontrado")
    return str(row["role_id"])


def _owners(db: sqlite3.Connection, organization_id: str) -> int:
    row = db.execute(
        """
        SELECT COUNT(*) AS n FROM memberships
        WHERE organization_id = ? AND role_id = 'owner' AND status = 'active'
        """,
        (organization_id,),
    ).fetchone()
    return int(row["n"])


def add_member(
    db: sqlite3.Connection, organization_id: str, email: str, role: str, actor_role: str
) -> dict[str, Any]:
    _check_role(role)
    if role == "owner" and actor_role != "owner":
        raise RoleChangeNotAllowedError("Solo un propietario puede nombrar propietarios")
    user = db.execute(
        "SELECT id FROM users WHERE email = ? AND is_active = 1 AND approval_status = 'approved'",
        (email.strip(),),
    ).fetchone()
    if user is None:
        raise UserNotFoundError("No existe un usuario activo con ese correo")
    try:
        db.execute(
            "INSERT INTO memberships (id, organization_id, user_id, role_id) VALUES (?, ?, ?, ?)",
            (str(uuid.uuid4()), organization_id, user["id"], role),
        )
    except sqlite3.IntegrityError as exc:
        raise AlreadyMemberError("El usuario ya es miembro") from exc
    return {"user_id": user["id"], "role": role}


def set_member_role(
    db: sqlite3.Connection, organization_id: str, user_id: str, role: str, actor_role: str
) -> None:
    _check_role(role)
    current = _current_role(db, organization_id, user_id)
    if "owner" in (role, current) and actor_role != "owner":
        raise RoleChangeNotAllowedError("Solo un propietario puede cambiar propietarios")
    if current == "owner" and role != "owner" and _owners(db, organization_id) <= 1:
        raise LastOwnerError("La organización debe conservar al menos un propietario")
    db.execute(
        "UPDATE memberships SET role_id = ? WHERE organization_id = ? AND user_id = ?",
        (role, organization_id, user_id),
    )


def remove_member(
    db: sqlite3.Connection, organization_id: str, user_id: str, actor_role: str
) -> None:
    current = _current_role(db, organization_id, user_id)
    if current == "owner":
        if actor_role != "owner":
            raise RoleChangeNotAllowedError("Solo un propietario puede quitar propietarios")
        if _owners(db, organization_id) <= 1:
            raise LastOwnerError("La organización debe conservar al menos un propietario")
    db.execute(
        "DELETE FROM memberships WHERE organization_id = ? AND user_id = ?",
        (organization_id, user_id),
    )
