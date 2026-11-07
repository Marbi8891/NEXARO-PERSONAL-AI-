import ast
import sqlite3
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path


class SQLiteConnectionTests(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test.db"

        source_path = (
            Path(__file__).resolve().parents[1]
            / "app"
            / "main.py"
        )

        tree = ast.parse(source_path.read_text())

        function_node = next(
            node for node in tree.body
            if isinstance(node, ast.FunctionDef)
            and node.name == "get_connection"
        )

        module = ast.Module(
            body=[function_node],
            type_ignores=[]
        )

        namespace = {
            "sqlite3": sqlite3,
            "contextmanager": contextmanager,
            "DATABASE_PATH": self.db_path
        }

        exec(
            compile(module, str(source_path), "exec"),
            namespace
        )

        self.get_connection = namespace["get_connection"]

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
            result = db.execute(
                "PRAGMA foreign_keys"
            ).fetchone()[0]

        self.assertEqual(result, 1)

    def test_valid_insert_is_committed(self):
        with self.get_connection() as db:
            db.execute(
                "INSERT INTO conversations (id) VALUES (?)",
                ("test-1",)
            )
            db.execute(
                """
                INSERT INTO messages (conversation_id, content)
                VALUES (?, ?)
                """,
                ("test-1", "Mensaje válido")
            )

        with self.get_connection() as db:
            count = db.execute(
                "SELECT COUNT(*) FROM messages"
            ).fetchone()[0]

        self.assertEqual(count, 1)

    def test_invalid_foreign_key_is_rejected_and_rolled_back(self):
        with self.assertRaises(sqlite3.IntegrityError):
            with self.get_connection() as db:
                db.execute(
                    """
                    INSERT INTO messages (conversation_id, content)
                    VALUES (?, ?)
                    """,
                    ("inexistente", "Mensaje inválido")
                )

        with self.get_connection() as db:
            count = db.execute(
                "SELECT COUNT(*) FROM messages"
            ).fetchone()[0]

        self.assertEqual(count, 0)

    def test_connection_is_closed_after_context(self):
        with self.get_connection() as db:
            connection = db

        with self.assertRaises(sqlite3.ProgrammingError):
            connection.execute("SELECT 1")


if __name__ == "__main__":
    unittest.main()
