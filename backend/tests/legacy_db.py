"""Fixture: base de datos con el esquema ANTERIOR a la migración de auth.

Reproduce la forma de la copia real (1 usuario, 4 sesiones, 11 conversaciones,
52 mensajes) sin depender de datos personales ni de ficheros ignorados por git.
"""
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.auth import create_session_token, hash_password, hash_session_token

LEGACY_EMAIL = "legacy@example.com"
LEGACY_PASSWORD = "legacy-password-123"


def create_legacy_database(path):
    """Crea la base legada y devuelve (user_id, token_de_sesion_viva)."""
    now = datetime.now(timezone.utc)
    user_id = "4ae04d4a-de7a-449b-be34-2ed02893cb28"
    live_token = create_session_token()

    connection = sqlite3.connect(path)
    try:
        connection.executescript("""
            CREATE TABLE conversations (
                id TEXT PRIMARY KEY,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                user_id TEXT REFERENCES users(id)
            );
            CREATE TABLE messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (conversation_id) REFERENCES conversations(id)
            );
            CREATE TABLE users (
                id TEXT PRIMARY KEY,
                email TEXT NOT NULL UNIQUE COLLATE NOCASE,
                password_hash TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE sessions (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                token_hash TEXT NOT NULL UNIQUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP NOT NULL,
                revoked_at TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );
            CREATE INDEX idx_conversations_user_id ON conversations(user_id);
            CREATE INDEX idx_sessions_user_id ON sessions(user_id);
        """)

        connection.execute(
            "INSERT INTO users (id, email, password_hash) VALUES (?, ?, ?)",
            (user_id, LEGACY_EMAIL, hash_password(LEGACY_PASSWORD)),
        )

        expires = (now + timedelta(days=7)).isoformat(timespec="seconds")
        revoked = now.isoformat(timespec="seconds")

        for index in range(3):
            connection.execute(
                """
                INSERT INTO sessions
                    (id, user_id, token_hash, expires_at, revoked_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    f"old-{index}",
                    user_id,
                    hash_session_token(create_session_token()),
                    expires,
                    revoked,
                ),
            )

        connection.execute(
            "INSERT INTO sessions (id, user_id, token_hash, expires_at) "
            "VALUES ('live', ?, ?, ?)",
            (user_id, hash_session_token(live_token), expires),
        )

        for index in range(11):
            connection.execute(
                "INSERT INTO conversations (id, user_id) VALUES (?, ?)",
                (f"conv-{index}", user_id),
            )

        for index in range(52):
            connection.execute(
                "INSERT INTO messages (conversation_id, role, content) "
                "VALUES (?, 'user', ?)",
                (f"conv-{index % 11}", f"mensaje {index}"),
            )

        connection.commit()
    finally:
        connection.close()

    return user_id, live_token
