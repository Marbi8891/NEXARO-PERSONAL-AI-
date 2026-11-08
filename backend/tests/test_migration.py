import hashlib
import shutil
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
BACKEND_DIR = TESTS_DIR.parent
sys.path.insert(0, str(TESTS_DIR))
sys.path.insert(0, str(BACKEND_DIR))

from app.auth import init_auth_schema
from legacy_db import create_legacy_database

REAL_BACKUP = (
    BACKEND_DIR.parent / "backups" / "nexaro-pre-auth-migration-20261108.db"
)

COUNTED_TABLES = ("users", "sessions", "conversations", "messages")


def open_db(path):
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def counts(connection):
    return {
        table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in COUNTED_TABLES
    }


def snapshot(connection):
    return {
        "schema": sorted(
            tuple(row)
            for row in connection.execute(
                "SELECT type, name, sql FROM sqlite_master"
            )
        ),
        "settings": [
            tuple(row)
            for row in connection.execute(
                "SELECT key, value FROM app_settings ORDER BY key"
            )
        ],
        "counts": counts(connection),
    }


def migrate(connection):
    # Mismo patrón que main.init_auth_database: transacción explícita.
    with connection:
        connection.execute("BEGIN IMMEDIATE")
        init_auth_schema(connection)


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class MigrationAssertions:
    def assert_migrated(self, connection, expected_counts):
        columns = {
            row["name"]: row
            for row in connection.execute("PRAGMA table_info(users)")
        }
        for name in ("role", "is_active", "approval_status"):
            self.assertIn(name, columns)

        user = connection.execute(
            "SELECT role, is_active, approval_status FROM users"
        ).fetchone()
        self.assertEqual(
            (user["role"], user["is_active"], user["approval_status"]),
            ("user", 1, "approved"),
        )

        self.assertEqual(counts(connection), expected_counts)
        self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])
        self.assertEqual(
            connection.execute("PRAGMA integrity_check").fetchone()[0], "ok"
        )
        self.assertEqual(
            connection.execute(
                "SELECT value FROM app_settings "
                "WHERE key = 'public_registration_enabled'"
            ).fetchone()[0],
            "0",
        )
        self.assertEqual(
            connection.execute(
                "SELECT COUNT(*) FROM users WHERE role = 'admin'"
            ).fetchone()[0],
            0,
            "la migración no debe crear administradores",
        )


class LegacyMigrationTests(MigrationAssertions, unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "legacy.db"
        create_legacy_database(self.path)

    def tearDown(self):
        self.temp.cleanup()

    def test_migration_preserves_data_and_applies_defaults(self):
        connection = open_db(self.path)
        try:
            migrate(connection)
            self.assert_migrated(
                connection,
                {"users": 1, "sessions": 4, "conversations": 11, "messages": 52},
            )
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM conversations WHERE user_id IS NOT NULL"
                ).fetchone()[0],
                11,
            )
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM sessions WHERE revoked_at IS NULL"
                ).fetchone()[0],
                1,
                "las sesiones existentes no deben modificarse",
            )
        finally:
            connection.close()

    def test_migration_is_idempotent(self):
        connection = open_db(self.path)
        try:
            migrate(connection)
            first = snapshot(connection)
            migrate(connection)
            migrate(connection)
            self.assertEqual(snapshot(connection), first)
        finally:
            connection.close()

    def test_failed_migration_rolls_back_completely(self):
        connection = open_db(self.path)
        try:
            # Sin 'conversations' el ALTER final falla, después de haber
            # añadido ya las columnas de 'users'.
            with connection:
                connection.execute("DROP TABLE messages")
                connection.execute("DROP TABLE conversations")

            with self.assertRaises(sqlite3.OperationalError):
                migrate(connection)

            columns = [
                row["name"] for row in connection.execute("PRAGMA table_info(users)")
            ]
            self.assertEqual(
                columns, ["id", "email", "password_hash", "created_at"]
            )
            self.assertIsNone(
                connection.execute(
                    "SELECT name FROM sqlite_master WHERE name = 'app_settings'"
                ).fetchone()
            )
        finally:
            connection.close()

    def test_missing_revoked_at_column_is_added(self):
        connection = open_db(self.path)
        try:
            with connection:
                connection.execute("ALTER TABLE sessions DROP COLUMN revoked_at")
            migrate(connection)
            names = [
                row["name"] for row in connection.execute("PRAGMA table_info(sessions)")
            ]
            self.assertIn("revoked_at", names)
        finally:
            connection.close()


@unittest.skipUnless(REAL_BACKUP.is_file(), "no hay copia real en backups/")
class RealBackupCopyTests(MigrationAssertions, unittest.TestCase):
    """Migra una COPIA de la copia de seguridad real; el original no se toca."""

    def test_real_backup_copy_migrates_and_original_is_untouched(self):
        before = sha256(REAL_BACKUP)

        with tempfile.TemporaryDirectory() as directory:
            copy = Path(directory) / "copy.db"
            shutil.copyfile(REAL_BACKUP, copy)

            connection = open_db(copy)
            try:
                migrate(connection)
                first = snapshot(connection)
                migrate(connection)
                self.assertEqual(snapshot(connection), first)
                self.assert_migrated(
                    connection,
                    {"users": 1, "sessions": 4, "conversations": 11, "messages": 52},
                )
            finally:
                connection.close()

        self.assertEqual(sha256(REAL_BACKUP), before)


if __name__ == "__main__":
    unittest.main()
