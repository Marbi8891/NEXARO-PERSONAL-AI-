import sqlite3
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.auth import (
    create_session_token,
    hash_password,
    hash_session_token,
    init_auth_schema,
    verify_password,
)


class AuthCoreTests(unittest.TestCase):
    def test_password_hash_and_verification(self):
        password = "UnaClaveDePrueba-2026!"
        encoded = hash_password(password)

        self.assertNotEqual(encoded, password)
        self.assertTrue(verify_password(password, encoded))
        self.assertFalse(verify_password("otra-clave", encoded))

    def test_password_hash_uses_unique_salts(self):
        password = "UnaClaveDePrueba-2026!"

        first = hash_password(password)
        second = hash_password(password)

        self.assertNotEqual(first, second)
        self.assertTrue(verify_password(password, first))
        self.assertTrue(verify_password(password, second))

    def test_short_password_is_rejected(self):
        with self.assertRaises(ValueError):
            hash_password("corta")

    def test_session_token_is_random_and_only_hash_is_stored(self):
        first = create_session_token()
        second = create_session_token()

        self.assertNotEqual(first, second)
        self.assertNotEqual(first, hash_session_token(first))
        self.assertEqual(
            hash_session_token(first),
            hash_session_token(first),
        )

    def test_schema_migrates_existing_conversations(self):
        db = sqlite3.connect(":memory:")
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")

        db.execute("""
            CREATE TABLE conversations (
                id TEXT PRIMARY KEY,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        db.execute("""
            CREATE TABLE messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                FOREIGN KEY (conversation_id) REFERENCES conversations(id)
            )
        """)
        db.execute(
            "INSERT INTO conversations (id) VALUES (?)",
            ("conversation-1",),
        )
        db.commit()

        init_auth_schema(db)
        init_auth_schema(db)

        columns = {
            row["name"]
            for row in db.execute("PRAGMA table_info(conversations)")
        }

        self.assertIn("user_id", columns)
        self.assertEqual(
            db.execute("SELECT COUNT(*) FROM conversations").fetchone()[0],
            1,
        )
        self.assertIsNone(
            db.execute(
                "SELECT user_id FROM conversations WHERE id = ?",
                ("conversation-1",),
            ).fetchone()[0]
        )
        self.assertIsNotNone(
            db.execute(
                "SELECT name FROM sqlite_master WHERE name = 'users'"
            ).fetchone()
        )
        self.assertIsNotNone(
            db.execute(
                "SELECT name FROM sqlite_master WHERE name = 'sessions'"
            ).fetchone()
        )

        db.close()



    def test_user_email_must_be_unique_case_insensitive(self):
        db = sqlite3.connect(":memory:")
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
        db.execute("""
            CREATE TABLE conversations (
                id TEXT PRIMARY KEY,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        init_auth_schema(db)

        db.execute(
            "INSERT INTO users (id, email, password_hash) VALUES (?, ?, ?)",
            ("user-1", "admin@example.com", "hash"),
        )

        with self.assertRaises(sqlite3.IntegrityError):
            db.execute(
                "INSERT INTO users (id, email, password_hash) VALUES (?, ?, ?)",
                ("user-2", "ADMIN@example.com", "hash"),
            )
        db.close()

    def test_session_requires_existing_user(self):
        db = sqlite3.connect(":memory:")
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
        db.execute("""
            CREATE TABLE conversations (
                id TEXT PRIMARY KEY,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        init_auth_schema(db)

        with self.assertRaises(sqlite3.IntegrityError):
            db.execute("""
                INSERT INTO sessions (id, user_id, token_hash, expires_at)
                VALUES (?, ?, ?, ?)
            """, ("session-1", "missing-user", "token-hash", "2030-01-01"))
        db.close()

    def test_conversation_can_be_assigned_to_existing_user(self):
        db = sqlite3.connect(":memory:")
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
        db.execute("""
            CREATE TABLE conversations (
                id TEXT PRIMARY KEY,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        init_auth_schema(db)

        db.execute(
            "INSERT INTO users (id, email, password_hash) VALUES (?, ?, ?)",
            ("user-1", "admin@example.com", "hash"),
        )
        db.execute(
            "INSERT INTO conversations (id, user_id) VALUES (?, ?)",
            ("conversation-1", "user-1"),
        )

        owner = db.execute(
            "SELECT user_id FROM conversations WHERE id = ?",
            ("conversation-1",),
        ).fetchone()["user_id"]

        self.assertEqual(owner, "user-1")
        db.close()




    def _create_session_test_database(self):
        import sqlite3
        from app.auth import init_auth_schema

        db = sqlite3.connect(":memory:")
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
        db.execute("""
            CREATE TABLE conversations (
                id TEXT PRIMARY KEY,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        init_auth_schema(db)
        db.execute(
            "INSERT INTO users (id, email, password_hash) VALUES (?, ?, ?)",
            ("session-user", "admin@example.com", "test-hash"),
        )
        return db

    def test_active_session_returns_user(self):
        from datetime import datetime, timezone, timedelta
        from app.auth import create_session, get_session_user

        db = self._create_session_test_database()
        now = datetime(2026, 11, 7, 12, 0, tzinfo=timezone.utc)

        token = create_session(db, "session-user", now=now)
        user = get_session_user(db, token, now=now + timedelta(minutes=1))

        self.assertIsNotNone(user)
        self.assertEqual(user["id"], "session-user")
        self.assertEqual(user["email"], "admin@example.com")
        db.close()

    def test_session_stores_only_token_hash(self):
        from datetime import datetime, timezone
        from app.auth import create_session, hash_session_token

        db = self._create_session_test_database()
        now = datetime(2026, 11, 7, 12, 0, tzinfo=timezone.utc)

        token = create_session(db, "session-user", now=now)
        row = db.execute(
            "SELECT token_hash FROM sessions"
        ).fetchone()

        self.assertEqual(row["token_hash"], hash_session_token(token))
        self.assertNotEqual(row["token_hash"], token)
        db.close()

    def test_expired_session_returns_no_user(self):
        from datetime import datetime, timezone, timedelta
        from app.auth import create_session, get_session_user

        db = self._create_session_test_database()
        now = datetime(2026, 11, 7, 12, 0, tzinfo=timezone.utc)

        token = create_session(
            db,
            "session-user",
            lifetime=timedelta(hours=1),
            now=now - timedelta(hours=2),
        )

        user = get_session_user(db, token, now=now)

        self.assertIsNone(user)
        db.close()

    def test_revoked_session_returns_no_user(self):
        from datetime import datetime, timezone
        from app.auth import create_session, get_session_user, revoke_session

        db = self._create_session_test_database()
        now = datetime(2026, 11, 7, 12, 0, tzinfo=timezone.utc)

        token = create_session(db, "session-user", now=now)

        self.assertTrue(revoke_session(db, token, now=now))
        self.assertIsNone(get_session_user(db, token, now=now))
        self.assertFalse(revoke_session(db, token, now=now))
        db.close()

    def test_unknown_session_returns_no_user(self):
        from app.auth import get_session_user

        db = self._create_session_test_database()

        self.assertIsNone(get_session_user(db, "token-inexistente"))
        db.close()

    def test_session_rejects_naive_datetime(self):
        from datetime import datetime
        from app.auth import create_session

        db = self._create_session_test_database()

        with self.assertRaises(ValueError):
            create_session(
                db,
                "session-user",
                now=datetime(2026, 11, 7, 12, 0),
            )

        db.close()




    def test_session_expires_at_exact_boundary(self):
        from datetime import datetime, timezone, timedelta
        from app.auth import create_session, get_session_user

        db = self._create_session_test_database()
        now = datetime(2026, 11, 7, 12, 0, tzinfo=timezone.utc)

        token = create_session(
            db,
            "session-user",
            lifetime=timedelta(hours=1),
            now=now,
        )

        user = get_session_user(
            db,
            token,
            now=now + timedelta(hours=1),
        )

        self.assertIsNone(user)
        db.close()

    def test_session_rejects_non_positive_lifetime(self):
        from datetime import datetime, timezone, timedelta
        from app.auth import create_session

        db = self._create_session_test_database()
        now = datetime(2026, 11, 7, 12, 0, tzinfo=timezone.utc)

        for lifetime in (
            timedelta(0),
            timedelta(seconds=-1),
        ):
            with self.subTest(lifetime=lifetime):
                with self.assertRaises(ValueError):
                    create_session(
                        db,
                        "session-user",
                        lifetime=lifetime,
                        now=now,
                    )

        db.close()

    def test_session_creation_can_be_rolled_back(self):
        from datetime import datetime, timezone
        from app.auth import create_session, get_session_user

        db = self._create_session_test_database()
        now = datetime(2026, 11, 7, 12, 0, tzinfo=timezone.utc)

        token = create_session(db, "session-user", now=now)
        db.rollback()

        self.assertIsNone(get_session_user(db, token, now=now))
        db.close()

    def test_password_verification_rejects_unsafe_scrypt_parameters(self):
        valid_hash = hash_password("UnaClaveDePrueba-2026!")
        parts = valid_hash.split("$")

        unsafe_hashes = []

        for index, value in ((1, "1073741824"), (2, "999999"), (3, "999999")):
            modified = parts.copy()
            modified[index] = value
            unsafe_hashes.append("$".join(modified))

        for encoded in unsafe_hashes:
            with self.subTest(encoded=encoded):
                self.assertFalse(
                    verify_password("UnaClaveDePrueba-2026!", encoded)
                )

    def test_password_verification_rejects_invalid_salt_and_hash_lengths(self):
        valid_hash = hash_password("UnaClaveDePrueba-2026!")
        parts = valid_hash.split("$")

        invalid_salt = parts.copy()
        invalid_salt[4] = "abcd"

        invalid_hash = parts.copy()
        invalid_hash[5] = "abcd"

        self.assertFalse(
            verify_password(
                "UnaClaveDePrueba-2026!",
                "$".join(invalid_salt),
            )
        )

        self.assertFalse(
            verify_password(
                "UnaClaveDePrueba-2026!",
                "$".join(invalid_hash),
            )
        )


    def _create_accounts_database(self):
        import sqlite3
        from app.auth import init_auth_schema

        db = sqlite3.connect(":memory:")
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
        db.execute("""
            CREATE TABLE conversations (
                id TEXT PRIMARY KEY,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        init_auth_schema(db)
        return db

    def test_public_registration_is_disabled_by_default(self):
        from app.auth import get_registration_enabled

        db = self._create_accounts_database()
        self.assertFalse(get_registration_enabled(db))
        db.close()

    def test_registration_setting_can_be_changed(self):
        from app.auth import (
            get_registration_enabled,
            set_registration_enabled,
        )

        db = self._create_accounts_database()
        set_registration_enabled(db, True)
        self.assertTrue(get_registration_enabled(db))
        set_registration_enabled(db, False)
        self.assertFalse(get_registration_enabled(db))
        db.close()

    def test_new_user_is_pending_and_never_admin(self):
        from app.auth import create_user, list_users

        db = self._create_accounts_database()
        user_id = create_user(
            db,
            "new.user@example.com",
            "UnaClaveSegura-2026!",
        )

        user = next(item for item in list_users(db) if item["id"] == user_id)
        self.assertEqual(user["role"], "user")
        self.assertEqual(user["approval_status"], "pending")
        self.assertEqual(user["is_active"], 0)
        db.close()

    def test_pending_user_session_is_rejected_until_approved(self):
        from datetime import datetime, timezone
        from app.auth import create_user, create_session, get_session_user, approve_user

        db = self._create_accounts_database()
        user_id = create_user(
            db,
            "pending@example.com",
            "UnaClaveSegura-2026!",
        )
        now = datetime(2026, 11, 7, 12, 0, tzinfo=timezone.utc)
        token = create_session(db, user_id, now=now)

        self.assertIsNone(get_session_user(db, token, now=now))
        self.assertTrue(approve_user(db, user_id))

        user = get_session_user(db, token, now=now)
        self.assertIsNotNone(user)
        self.assertEqual(user["role"], "user")
        db.close()

    def test_rejected_user_cannot_use_existing_session(self):
        from datetime import datetime, timezone
        from app.auth import create_user, create_session, get_session_user, reject_user

        db = self._create_accounts_database()
        user_id = create_user(
            db,
            "rejected@example.com",
            "UnaClaveSegura-2026!",
            approved=True,
        )
        now = datetime(2026, 11, 7, 12, 0, tzinfo=timezone.utc)
        token = create_session(db, user_id, now=now)

        self.assertIsNotNone(get_session_user(db, token, now=now))
        self.assertTrue(reject_user(db, user_id))
        self.assertIsNone(get_session_user(db, token, now=now))
        db.close()

    def test_deactivated_user_cannot_use_existing_session(self):
        from datetime import datetime, timezone
        from app.auth import create_user, create_session, get_session_user, set_user_active

        db = self._create_accounts_database()
        user_id = create_user(
            db,
            "inactive@example.com",
            "UnaClaveSegura-2026!",
            approved=True,
        )
        now = datetime(2026, 11, 7, 12, 0, tzinfo=timezone.utc)
        token = create_session(db, user_id, now=now)

        self.assertTrue(set_user_active(db, user_id, False))
        self.assertIsNone(get_session_user(db, token, now=now))
        db.close()

    def test_duplicate_account_email_is_rejected(self):
        import sqlite3
        from app.auth import create_user

        db = self._create_accounts_database()
        create_user(db, "duplicate@example.com", "UnaClaveSegura-2026!")

        with self.assertRaises(sqlite3.IntegrityError):
            create_user(db, "DUPLICATE@example.com", "OtraClaveSegura-2026!")
        db.close()

    def test_invalid_role_is_rejected(self):
        from app.auth import create_user, set_user_role

        db = self._create_accounts_database()
        user_id = create_user(
            db,
            "role@example.com",
            "UnaClaveSegura-2026!",
        )

        with self.assertRaises(ValueError):
            set_user_role(db, user_id, "superadmin")
        db.close()


if __name__ == "__main__":
    unittest.main()
