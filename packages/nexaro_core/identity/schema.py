"""Esquema de identidad: migración aditiva e idempotente.

El llamador abre la transacción (`begin_write`). Nota: también añade `conversations.user_id`
porque las conversaciones pertenecen a un usuario; la migración versionada (ADR-0003) lo separará.
"""

import sqlite3


def init_identity_schema(db: sqlite3.Connection) -> None:
    """Crea y amplía el esquema de autenticación de forma aditiva."""
    db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            email TEXT NOT NULL UNIQUE COLLATE NOCASE,
            password_hash TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    user_columns = {row["name"] for row in db.execute("PRAGMA table_info(users)").fetchall()}

    additions = (
        ("role", "TEXT NOT NULL DEFAULT 'user' CHECK (role IN ('admin', 'user'))"),
        ("is_active", "INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1))"),
        (
            "approval_status",
            "TEXT NOT NULL DEFAULT 'approved' "
            "CHECK (approval_status IN ('pending', 'approved', 'rejected'))",
        ),
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

    session_columns = {row["name"] for row in db.execute("PRAGMA table_info(sessions)").fetchall()}

    if "revoked_at" not in session_columns:
        db.execute("ALTER TABLE sessions ADD COLUMN revoked_at TIMESTAMP")

    conversation_columns = {
        row["name"] for row in db.execute("PRAGMA table_info(conversations)").fetchall()
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
