import sqlite3
import tempfile
import unittest
from pathlib import Path

from nexaro_core.database import Database


class SQLiteConnectionTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test.db"

        self.get_connection = Database(self.db_path).connect

        with self.get_connection() as db:
            db.execute("""
                CREATE TABLE conversations (
                    id TEXT PRIMARY KEY
                )
            """)

            db.execute("""
                CREATE TABLE messages (
                    id INTEGER PRIMARY KEY,
                    conversation_id TEXT NOT NULL,
                    content TEXT NOT NULL,
                    FOREIGN KEY (conversation_id)
                        REFERENCES conversations(id)
                )
            """)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_foreign_keys_enabled(self):
        with self.get_connection() as db:
            result = db.execute("PRAGMA foreign_keys").fetchone()[0]

        self.assertEqual(result, 1)

    def test_valid_insert_is_committed(self):
        with self.get_connection() as db:
            db.execute("INSERT INTO conversations (id) VALUES (?)", ("test-1",))
            db.execute(
                """
                INSERT INTO messages (conversation_id, content)
                VALUES (?, ?)
                """,
                ("test-1", "Mensaje válido"),
            )

        with self.get_connection() as db:
            count = db.execute("SELECT COUNT(*) FROM messages").fetchone()[0]

        self.assertEqual(count, 1)

    def test_invalid_foreign_key_is_rejected_and_rolled_back(self):
        with self.assertRaises(sqlite3.IntegrityError), self.get_connection() as db:
            db.execute(
                """
                    INSERT INTO messages (conversation_id, content)
                    VALUES (?, ?)
                    """,
                ("inexistente", "Mensaje inválido"),
            )

        with self.get_connection() as db:
            count = db.execute("SELECT COUNT(*) FROM messages").fetchone()[0]

        self.assertEqual(count, 0)

    def test_connection_is_closed_after_context(self):
        with self.get_connection() as db:
            connection = db

        with self.assertRaises(sqlite3.ProgrammingError):
            connection.execute("SELECT 1")


if __name__ == "__main__":
    unittest.main()


def test_connections_use_wal_and_wait_for_locks(tmp_path) -> None:
    database = Database(tmp_path / "wal.db")
    with database.connect() as db:
        assert db.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert db.execute("PRAGMA busy_timeout").fetchone()[0] >= 10_000
