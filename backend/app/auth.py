import hashlib
import hmac
import secrets
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone


SCRYPT_N = 2**14
SCRYPT_R = 8
SCRYPT_P = 1
SCRYPT_MAXMEM = 128 * 1024 * 1024


def hash_password(password: str) -> str:
    if not isinstance(password, str) or len(password) < 12:
        raise ValueError("La contraseña debe tener al menos 12 caracteres")

    salt = secrets.token_bytes(16)
    derived = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=SCRYPT_N,
        r=SCRYPT_R,
        p=SCRYPT_P,
        dklen=64,
        maxmem=SCRYPT_MAXMEM,
    )

    return "scrypt${}${}${}${}${}".format(
        SCRYPT_N,
        SCRYPT_R,
        SCRYPT_P,
        salt.hex(),
        derived.hex(),
    )


def verify_password(password: str, encoded: str) -> bool:
    if not isinstance(password, str) or not isinstance(encoded, str):
        return False

    try:
        algorithm, n, r, p, salt_hex, expected_hex = encoded.split("$")

        if algorithm != "scrypt":
            return False

        n = int(n)
        r = int(r)
        p = int(p)

        if (n, r, p) != (SCRYPT_N, SCRYPT_R, SCRYPT_P):
            return False

        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(expected_hex)

        if len(salt) != 16 or len(expected) != 64:
            return False

        actual = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=SCRYPT_N,
            r=SCRYPT_R,
            p=SCRYPT_P,
            dklen=64,
            maxmem=SCRYPT_MAXMEM,
        )

        return hmac.compare_digest(actual, expected)

    except (ValueError, TypeError, MemoryError, OverflowError):
        return False


def create_session_token() -> str:
    return secrets.token_urlsafe(32)


def hash_session_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()



def _utc_timestamp(value=None):
    if value is None:
        value = datetime.now(timezone.utc)

    if value.tzinfo is None:
        raise ValueError("La fecha debe incluir zona horaria")

    return value.astimezone(timezone.utc).isoformat(timespec="seconds")


def create_session(
    db: sqlite3.Connection,
    user_id: str,
    lifetime: timedelta = timedelta(days=7),
    now: datetime | None = None,
) -> str:
    """Crea una sesión sin confirmar la transacción de SQLite.

    El llamador es responsable de hacer commit o rollback.
    """
    if not isinstance(lifetime, timedelta) or lifetime.total_seconds() <= 0:
        raise ValueError("La duración de la sesión debe ser positiva")

    base_time = now or datetime.now(timezone.utc)
    _utc_timestamp(base_time)
    expires_at = _utc_timestamp(base_time + lifetime)

    token = create_session_token()
    session_id = str(uuid.uuid4())

    db.execute(
        """
        INSERT INTO sessions (id, user_id, token_hash, expires_at)
        VALUES (?, ?, ?, ?)
        """,
        (session_id, user_id, hash_session_token(token), expires_at),
    )

    return token


def get_session_user(
    db: sqlite3.Connection,
    token: str,
    now: datetime | None = None,
):
    if not isinstance(token, str) or not token:
        return None

    current_time = _utc_timestamp(now)

    return db.execute(
        """
        SELECT users.id, users.email, users.role
        FROM sessions
        JOIN users ON users.id = sessions.user_id
        WHERE sessions.token_hash = ?
          AND sessions.revoked_at IS NULL
          AND sessions.expires_at > ?
          AND users.is_active = 1
          AND users.approval_status = 'approved'
        LIMIT 1
        """,
        (hash_session_token(token), current_time),
    ).fetchone()

def revoke_session(
    db: sqlite3.Connection,
    token: str,
    now: datetime | None = None,
) -> bool:
    if not isinstance(token, str) or not token:
        return False

    revoked_at = _utc_timestamp(now)

    cursor = db.execute(
        """
        UPDATE sessions
        SET revoked_at = ?
        WHERE token_hash = ?
          AND revoked_at IS NULL
        """,
        (revoked_at, hash_session_token(token)),
    )

    return cursor.rowcount == 1


def init_auth_schema(db: sqlite3.Connection) -> None:
    """Crea y amplía el esquema de autenticación de forma aditiva."""
    db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            email TEXT NOT NULL UNIQUE COLLATE NOCASE,
            password_hash TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    user_columns = {
        row["name"]
        for row in db.execute("PRAGMA table_info(users)").fetchall()
    }

    additions = (
        ("role", "TEXT NOT NULL DEFAULT 'user' CHECK (role IN ('admin', 'user'))"),
        ("is_active", "INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1))"),
        ("approval_status", "TEXT NOT NULL DEFAULT 'approved' CHECK (approval_status IN ('pending', 'approved', 'rejected'))"),
    )

    for name, definition in additions:
        if name not in user_columns:
            db.execute(f"ALTER TABLE users ADD COLUMN {name} {definition}")

    db.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            token_hash TEXT NOT NULL UNIQUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP NOT NULL,
            revoked_at TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    session_columns = {
        row["name"]
        for row in db.execute("PRAGMA table_info(sessions)").fetchall()
    }

    if "revoked_at" not in session_columns:
        db.execute("ALTER TABLE sessions ADD COLUMN revoked_at TIMESTAMP")

    conversation_columns = {
        row["name"]
        for row in db.execute("PRAGMA table_info(conversations)").fetchall()
    }

    if "user_id" not in conversation_columns:
        db.execute("""
            ALTER TABLE conversations
            ADD COLUMN user_id TEXT REFERENCES users(id)
        """)

    db.execute("""
        CREATE INDEX IF NOT EXISTS idx_conversations_user_id
        ON conversations(user_id)
    """)

    db.execute("""
        CREATE INDEX IF NOT EXISTS idx_sessions_user_id
        ON sessions(user_id)
    """)

    db.execute("""
        CREATE TABLE IF NOT EXISTS app_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    db.execute("""
        INSERT OR IGNORE INTO app_settings (key, value)
        VALUES ('public_registration_enabled', '0')
    """)


def create_user(
    db: sqlite3.Connection,
    email: str,
    password: str,
    approved: bool = False,
) -> str:
    """Crea una cuenta normal. Nunca asigna el rol admin."""
    if not isinstance(email, str):
        raise ValueError("Correo electrónico no válido")

    normalized_email = email.strip().lower()

    if (
        len(normalized_email) > 254
        or normalized_email.count("@") != 1
        or "." not in normalized_email.rsplit("@", 1)[-1]
    ):
        raise ValueError("Correo electrónico no válido")

    password_hash = hash_password(password)
    user_id = str(uuid.uuid4())
    status = "approved" if approved else "pending"
    active = 1 if approved else 0

    db.execute(
        """
        INSERT INTO users (
            id, email, password_hash, role, is_active, approval_status
        )
        VALUES (?, ?, ?, 'user', ?, ?)
        """,
        (user_id, normalized_email, password_hash, active, status),
    )

    return user_id


def approve_user(db: sqlite3.Connection, user_id: str) -> bool:
    cursor = db.execute(
        """
        UPDATE users
        SET approval_status = 'approved', is_active = 1
        WHERE id = ?
        """,
        (user_id,),
    )
    return cursor.rowcount == 1


def reject_user(db: sqlite3.Connection, user_id: str) -> bool:
    cursor = db.execute(
        """
        UPDATE users
        SET approval_status = 'rejected', is_active = 0
        WHERE id = ?
        """,
        (user_id,),
    )
    return cursor.rowcount == 1


def set_user_active(
    db: sqlite3.Connection,
    user_id: str,
    active: bool,
) -> bool:
    if not isinstance(active, bool):
        raise ValueError("El estado activo debe ser booleano")

    cursor = db.execute(
        "UPDATE users SET is_active = ? WHERE id = ?",
        (1 if active else 0, user_id),
    )
    return cursor.rowcount == 1


def set_user_role(
    db: sqlite3.Connection,
    user_id: str,
    role: str,
) -> bool:
    if role not in ("admin", "user"):
        raise ValueError("Rol no válido")

    cursor = db.execute(
        "UPDATE users SET role = ? WHERE id = ?",
        (role, user_id),
    )
    return cursor.rowcount == 1


def count_active_admins(
    db: sqlite3.Connection,
    excluding_user_id: str | None = None,
) -> int:
    """Cuenta administradores activos y aprobados, opcionalmente sin uno."""
    row = db.execute(
        """
        SELECT COUNT(*) AS total
        FROM users
        WHERE role = 'admin'
          AND is_active = 1
          AND approval_status = 'approved'
          AND id IS NOT ?
        """,
        (excluding_user_id,),
    ).fetchone()
    return row["total"]


def list_users(db: sqlite3.Connection) -> list[dict]:
    rows = db.execute(
        """
        SELECT id, email, role, is_active, approval_status, created_at
        FROM users
        ORDER BY created_at DESC, email COLLATE NOCASE
        """
    ).fetchall()
    return [dict(row) for row in rows]


def get_registration_enabled(db: sqlite3.Connection) -> bool:
    row = db.execute(
        """
        SELECT value FROM app_settings
        WHERE key = 'public_registration_enabled'
        """
    ).fetchone()
    return row is not None and row["value"] == "1"


def set_registration_enabled(
    db: sqlite3.Connection,
    enabled: bool,
) -> None:
    if not isinstance(enabled, bool):
        raise ValueError("El estado del registro debe ser booleano")

    db.execute(
        """
        INSERT INTO app_settings (key, value, updated_at)
        VALUES ('public_registration_enabled', ?, CURRENT_TIMESTAMP)
        ON CONFLICT(key) DO UPDATE SET
            value = excluded.value,
            updated_at = CURRENT_TIMESTAMP
        """,
        ("1" if enabled else "0",),
    )
