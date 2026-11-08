import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
BACKEND_DIR = TESTS_DIR.parent
sys.path.insert(0, str(TESTS_DIR))

from legacy_db import LEGACY_EMAIL, create_legacy_database


class BootstrapAdminTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Path(self.temp.name) / "nexaro.db"
        self.user_id, _ = create_legacy_database(self.db)

    def tearDown(self):
        self.temp.cleanup()

    def run_script(self, *extra, env_email=None):
        env = {"DATABASE_PATH": str(self.db), "PYTHONDONTWRITEBYTECODE": "1"}
        if env_email:
            env["ADMIN_EMAIL"] = env_email

        return subprocess.run(
            [
                sys.executable, "-B", "-m", "app.bootstrap_admin",
                "--confirm-database", str(self.db), *extra,
            ],
            cwd=BACKEND_DIR,
            env=env,
            capture_output=True,
            text=True,
            input="",
            timeout=60,
        )

    def user_row(self):
        connection = sqlite3.connect(self.db)
        connection.row_factory = sqlite3.Row
        try:
            columns = [r[1] for r in connection.execute("PRAGMA table_info(users)")]
            if "role" not in columns:
                return None
            return connection.execute(
                "SELECT role, is_active, approval_status, password_hash FROM users"
            ).fetchone()
        finally:
            connection.close()

    def test_existing_account_is_not_touched_without_explicit_flag(self):
        result = self.run_script("--email", LEGACY_EMAIL)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("--promote-existing", result.stdout + result.stderr)
        self.assertIsNone(self.user_row(), "no debe migrar ni modificar nada")
        self.assertEqual(list(self.db.parent.glob("*.pre-admin-*")), [])

    def test_email_is_required_and_not_hardcoded(self):
        result = self.run_script()
        self.assertNotEqual(result.returncode, 0)
        self.assertIsNone(self.user_row())

    def test_promote_existing_keeps_password_and_data(self):
        connection = sqlite3.connect(self.db)
        before_hash = connection.execute(
            "SELECT password_hash FROM users"
        ).fetchone()[0]
        connection.close()

        result = self.run_script("--promote-existing", env_email=LEGACY_EMAIL)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

        row = self.user_row()
        self.assertEqual(
            (row["role"], row["is_active"], row["approval_status"]),
            ("admin", 1, "approved"),
        )
        self.assertEqual(row["password_hash"], before_hash)
        self.assertEqual(len(list(self.db.parent.glob("*.pre-admin-*"))), 1)

        connection = sqlite3.connect(self.db)
        try:
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM sessions").fetchone()[0], 4
            )
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM messages").fetchone()[0], 52
            )
        finally:
            connection.close()

    def test_wrong_confirmation_path_changes_nothing(self):
        result = subprocess.run(
            [
                sys.executable, "-B", "-m", "app.bootstrap_admin",
                "--confirm-database", str(self.db) + ".otra",
                "--email", LEGACY_EMAIL, "--promote-existing",
            ],
            cwd=BACKEND_DIR,
            env={"DATABASE_PATH": str(self.db), "PYTHONDONTWRITEBYTECODE": "1"},
            capture_output=True,
            text=True,
            input="",
            timeout=60,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIsNone(self.user_row())


if __name__ == "__main__":
    unittest.main()
