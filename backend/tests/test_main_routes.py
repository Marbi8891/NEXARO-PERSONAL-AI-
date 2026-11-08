"""Pruebas de integración de las rutas FastAPI (autenticación, autorización,
arranque y aislamiento de datos). Usan una base temporal y no tocan Ollama."""
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

TESTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TESTS_DIR))
sys.path.insert(0, str(TESTS_DIR.parent))

_TEMP = tempfile.TemporaryDirectory()
DB_PATH = Path(_TEMP.name) / "routes.db"
ORIGIN = "http://127.0.0.1:8001"

os.environ["DATABASE_PATH"] = str(DB_PATH)
os.environ["ALLOWED_ORIGINS"] = ORIGIN
os.environ.pop("COOKIE_SECURE", None)

from fastapi import HTTPException
from fastapi.testclient import TestClient

from app import main
from app.auth import create_user
from legacy_db import LEGACY_EMAIL, LEGACY_PASSWORD, create_legacy_database

PASSWORD = "correct-horse-battery"
HEADERS = {"Origin": ORIGIN}


def tearDownModule():
    _TEMP.cleanup()


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


class FakeOllama:
    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, url, json=None):
        return FakeResponse({"message": {"content": "respuesta de prueba"}})

    async def get(self, url):
        return FakeResponse({"models": []})


class RouteTestCase(unittest.TestCase):
    def setUp(self):
        if DB_PATH.exists():
            DB_PATH.unlink()
        main._login_attempts.clear()
        self._clients = []

    def tearDown(self):
        for client in reversed(self._clients):
            client.__exit__(None, None, None)

    def start(self):
        """Arranca la app (ejecuta lifespan: init_database + migración auth)."""
        client = TestClient(main.app)
        client.__enter__()
        self._clients.append(client)
        return client

    def extra_client(self):
        return TestClient(main.app)

    def add_user(self, email, *, role="user", approved=True, active=True):
        with main.get_connection() as db:
            user_id = create_user(db, email, PASSWORD, approved=approved)
            db.execute(
                "UPDATE users SET role = ?, is_active = ? WHERE id = ?",
                (role, 1 if active else 0, user_id),
            )
        return user_id

    def login(self, client, email, password=PASSWORD):
        return client.post(
            "/api/auth/login",
            json={"email": email, "password": password},
            headers=HEADERS,
        )

    def logged_in(self, email, **kwargs):
        self.add_user(email, **kwargs)
        client = self.extra_client()
        self.assertEqual(self.login(client, email).status_code, 200)
        return client


class StartupTests(RouteTestCase):
    def test_lifespan_migrates_legacy_database_and_keeps_session_valid(self):
        user_id, token = create_legacy_database(DB_PATH)

        client = self.start()
        client.cookies.set(main.COOKIE_NAME, token)

        response = client.get("/api/auth/me")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["user"]["id"], user_id)
        self.assertEqual(response.json()["user"]["role"], "user")

        with main.get_connection() as db:
            counts = {
                t: db.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                for t in ("users", "sessions", "conversations", "messages")
            }
            admins = db.execute(
                "SELECT COUNT(*) FROM users WHERE role = 'admin'"
            ).fetchone()[0]
            registration = main.get_registration_enabled(db)

        self.assertEqual(
            counts,
            {"users": 1, "sessions": 4, "conversations": 11, "messages": 52},
        )
        self.assertEqual(admins, 0)
        self.assertFalse(registration)

        # El usuario migrado puede seguir entrando con su contraseña.
        self.assertEqual(
            self.login(self.extra_client(), LEGACY_EMAIL, LEGACY_PASSWORD).status_code,
            200,
        )

    def test_fresh_database_starts_with_registration_disabled_and_no_admin(self):
        self.start()

        with main.get_connection() as db:
            self.assertFalse(main.get_registration_enabled(db))
            self.assertEqual(
                db.execute("SELECT COUNT(*) FROM users").fetchone()[0], 0
            )

    def test_restart_is_idempotent(self):
        create_legacy_database(DB_PATH)
        first = self.start()
        first.__exit__(None, None, None)
        self._clients.remove(first)
        self.start()  # segundo arranque sobre la base ya migrada

    def test_migration_failure_aborts_startup_and_rolls_back(self):
        create_legacy_database(DB_PATH)

        def broken_migration(db):
            db.execute("ALTER TABLE users ADD COLUMN role TEXT DEFAULT 'user'")
            raise RuntimeError("fallo simulado")

        with patch.object(main, "init_auth_schema", broken_migration):
            with self.assertLogs("nexaro", level="ERROR"):
                with self.assertRaises(RuntimeError):
                    with TestClient(main.app):
                        pass

        connection = sqlite3.connect(DB_PATH)
        try:
            columns = [r[1] for r in connection.execute("PRAGMA table_info(users)")]
        finally:
            connection.close()

        self.assertNotIn("role", columns)


class LoginTests(RouteTestCase):
    def setUp(self):
        super().setUp()
        self.client = self.start()

    def test_login_sets_secure_session_cookie(self):
        self.add_user("a@example.com")
        response = self.login(self.client, "a@example.com")

        self.assertEqual(response.status_code, 200)
        cookie = response.headers["set-cookie"].lower()
        self.assertIn("httponly", cookie)
        self.assertIn("samesite=strict", cookie)
        self.assertIn("path=/", cookie)
        self.assertIn("max-age=", cookie)
        self.assertNotIn("password", response.text.lower())

        me = self.client.get("/api/auth/me")
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.json()["user"]["email"], "a@example.com")

    def test_login_is_case_insensitive_on_email(self):
        self.add_user("a@example.com")
        self.assertEqual(self.login(self.client, "A@Example.COM").status_code, 200)

    def test_wrong_password_and_unknown_user_are_indistinguishable(self):
        self.add_user("a@example.com")
        wrong = self.login(self.client, "a@example.com", "otra-clave-distinta")
        unknown = self.login(self.client, "nadie@example.com")

        self.assertEqual(wrong.status_code, 401)
        self.assertEqual(unknown.status_code, 401)
        self.assertEqual(wrong.json(), unknown.json())

    def test_pending_rejected_and_inactive_accounts_cannot_login(self):
        self.add_user("pending@example.com", approved=False)
        self.add_user("inactive@example.com", active=False)

        for email in ("pending@example.com", "inactive@example.com"):
            self.assertEqual(self.login(self.client, email).status_code, 401)

    def test_login_without_valid_origin_is_forbidden(self):
        self.add_user("a@example.com")
        payload = {"email": "a@example.com", "password": PASSWORD}

        self.assertEqual(
            self.client.post("/api/auth/login", json=payload).status_code, 403
        )
        self.assertEqual(
            self.client.post(
                "/api/auth/login",
                json=payload,
                headers={"Origin": "https://evil.example"},
            ).status_code,
            403,
        )

    def test_unknown_user_still_runs_password_verification(self):
        with patch.object(main, "verify_password", return_value=False) as verify:
            self.login(self.client, "nadie@example.com")
        verify.assert_called_once()

    def test_protected_routes_require_authentication(self):
        for method, path in (
            ("get", "/api/auth/me"),
            ("get", "/api/conversations"),
            ("get", "/api/conversations/x"),
            ("post", "/api/chat"),
            ("get", "/api/admin/users"),
        ):
            response = getattr(self.client, method)(path, headers=HEADERS)
            self.assertEqual(response.status_code, 401, path)

    def test_logout_revokes_the_session_server_side(self):
        self.add_user("a@example.com")
        self.login(self.client, "a@example.com")
        token = self.client.cookies.get(main.COOKIE_NAME)

        self.assertEqual(
            self.client.post("/api/auth/logout", headers=HEADERS).status_code, 200
        )

        replay = self.extra_client()
        replay.cookies.set(main.COOKIE_NAME, token)
        self.assertEqual(replay.get("/api/auth/me").status_code, 401)

    def test_logout_requires_valid_origin(self):
        self.assertEqual(self.client.post("/api/auth/logout").status_code, 403)


class RateLimitTests(RouteTestCase):
    def setUp(self):
        super().setUp()
        self.client = self.start()

    def test_account_is_locked_after_repeated_failures(self):
        self.add_user("a@example.com")

        for _ in range(main.LOGIN_MAX_ATTEMPTS):
            self.assertEqual(
                self.login(self.client, "a@example.com", "mala-clave-1234").status_code,
                401,
            )

        # Ni siquiera la contraseña correcta pasa mientras dure el bloqueo.
        self.assertEqual(self.login(self.client, "a@example.com").status_code, 429)

    def test_successful_login_does_not_reset_the_ip_counter(self):
        self.add_user("valid@example.com")
        failures = main.LOGIN_MAX_ATTEMPTS - 1

        for index in range(failures):
            self.login(self.client, f"x{index}@example.com", "mala-clave-1234")

        self.assertEqual(self.login(self.client, "valid@example.com").status_code, 200)

        self.login(self.client, "y@example.com", "mala-clave-1234")
        self.assertEqual(self.login(self.client, "valid@example.com").status_code, 429)

    def test_tracked_keys_are_bounded(self):
        with patch.object(main, "LOGIN_MAX_TRACKED_KEYS", 5):
            for index in range(20):
                main.record_login_attempt(f"email:{index}")
        self.assertLessEqual(len(main._login_attempts), 5)


class AdminTests(RouteTestCase):
    def setUp(self):
        super().setUp()
        self.start()
        self.admin_id = self.add_user("admin@example.com", role="admin")
        self.admin = self.extra_client()
        self.login(self.admin, "admin@example.com")

    def test_admin_routes_reject_normal_users(self):
        user = self.logged_in("user@example.com")

        self.assertEqual(user.get("/api/admin/users").status_code, 403)
        self.assertEqual(
            user.post(
                "/api/admin/users",
                json={"email": "n@example.com", "password": PASSWORD},
                headers=HEADERS,
            ).status_code,
            403,
        )
        self.assertEqual(
            user.patch(
                "/api/admin/settings/registration",
                json={"enabled": True},
                headers=HEADERS,
            ).status_code,
            403,
        )

    def test_admin_list_never_exposes_password_hashes(self):
        response = self.admin.get("/api/admin/users")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("password", response.text.lower())
        self.assertFalse(response.json()["public_registration_enabled"])

    def test_admin_actions_require_origin(self):
        self.assertEqual(
            self.admin.patch(
                "/api/admin/settings/registration", json={"enabled": True}
            ).status_code,
            403,
        )

    def test_admin_created_user_is_never_admin(self):
        response = self.admin.post(
            "/api/admin/users",
            json={"email": "new@example.com", "password": PASSWORD},
            headers=HEADERS,
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["role"], "user")

        short = self.admin.post(
            "/api/admin/users",
            json={"email": "short@example.com", "password": "corta"},
            headers=HEADERS,
        )
        self.assertEqual(short.status_code, 422)

    def test_public_registration_flow(self):
        public = self.extra_client()
        body = {"email": "new@example.com", "password": PASSWORD}

        self.assertEqual(
            public.post("/api/auth/register", json=body, headers=HEADERS).status_code,
            403,
        )

        self.assertEqual(
            self.admin.patch(
                "/api/admin/settings/registration",
                json={"enabled": True},
                headers=HEADERS,
            ).status_code,
            200,
        )

        created = public.post("/api/auth/register", json=body, headers=HEADERS)
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.json()["approval_status"], "pending")
        self.assertEqual(self.login(public, "new@example.com").status_code, 401)

        user_id = created.json()["user_id"]
        self.assertEqual(
            self.admin.post(
                f"/api/admin/users/{user_id}/approve", headers=HEADERS
            ).status_code,
            200,
        )
        self.assertEqual(self.login(public, "new@example.com").status_code, 200)
        self.assertEqual(public.get("/api/auth/me").json()["user"]["role"], "user")

    def test_reject_and_deactivate_revoke_live_sessions(self):
        for action in ("reject", "deactivate"):
            email = f"{action}@example.com"
            user = self.logged_in(email)
            user_id = self.user_id(email)

            if action == "reject":
                response = self.admin.post(
                    f"/api/admin/users/{user_id}/reject", headers=HEADERS
                )
            else:
                response = self.admin.patch(
                    f"/api/admin/users/{user_id}/active",
                    json={"active": False},
                    headers=HEADERS,
                )

            self.assertEqual(response.status_code, 200)
            self.assertEqual(user.get("/api/auth/me").status_code, 401, action)

    def test_admin_cannot_reject_or_deactivate_self(self):
        self.assertEqual(
            self.admin.post(
                f"/api/admin/users/{self.admin_id}/reject", headers=HEADERS
            ).status_code,
            400,
        )
        self.assertEqual(
            self.admin.patch(
                f"/api/admin/users/{self.admin_id}/active",
                json={"active": False},
                headers=HEADERS,
            ).status_code,
            400,
        )
        self.assertEqual(self.admin.get("/api/auth/me").status_code, 200)

    def test_last_active_admin_is_protected(self):
        with main.get_connection() as db:
            with self.assertRaises(HTTPException) as caught:
                main.ensure_not_last_admin(db, self.admin_id)
            self.assertEqual(caught.exception.status_code, 400)

        other = self.add_user("admin2@example.com", role="admin")
        with main.get_connection() as db:
            main.ensure_not_last_admin(db, self.admin_id)  # ya no es el último
            main.ensure_not_last_admin(db, other)

    def test_unknown_user_returns_404(self):
        self.assertEqual(
            self.admin.post(
                "/api/admin/users/nope/approve", headers=HEADERS
            ).status_code,
            404,
        )

    def user_id(self, email):
        with main.get_connection() as db:
            return db.execute(
                "SELECT id FROM users WHERE email = ?", (email,)
            ).fetchone()["id"]


class ConversationIsolationTests(RouteTestCase):
    def setUp(self):
        super().setUp()
        self.start()
        self.alice = self.logged_in("alice@example.com")
        self.bob = self.logged_in("bob@example.com")

    def chat(self, client, message="hola", conversation_id=None):
        body = {"message": message}
        if conversation_id:
            body["conversation_id"] = conversation_id
        with patch.object(main.httpx, "AsyncClient", FakeOllama):
            return client.post("/api/chat", json=body, headers=HEADERS)

    def test_users_cannot_read_or_write_each_others_conversations(self):
        reply = self.chat(self.alice, "secreto de alice")
        self.assertEqual(reply.status_code, 200)
        self.assertEqual(reply.json()["answer"], "respuesta de prueba")
        conversation_id = reply.json()["conversation_id"]

        self.assertEqual(
            self.alice.get(f"/api/conversations/{conversation_id}").status_code, 200
        )
        self.assertEqual(
            self.bob.get(f"/api/conversations/{conversation_id}").status_code, 404
        )
        self.assertEqual(
            self.chat(self.bob, "intruso", conversation_id).status_code, 404
        )
        self.assertEqual(self.bob.get("/api/conversations").json()["conversations"], [])
        self.assertEqual(
            len(self.alice.get("/api/conversations").json()["conversations"]), 1
        )

    def test_conversation_id_length_is_bounded(self):
        response = self.alice.post(
            "/api/chat",
            json={"message": "hola", "conversation_id": "x" * 65},
            headers=HEADERS,
        )
        self.assertEqual(response.status_code, 422)

    def test_ollama_failure_returns_generic_error(self):
        class Broken(FakeOllama):
            async def post(self, url, json=None):
                raise RuntimeError("detalle interno http://ollama:11434")

        with patch.object(main.httpx, "AsyncClient", Broken):
            response = self.alice.post(
                "/api/chat", json={"message": "hola"}, headers=HEADERS
            )

        self.assertEqual(response.status_code, 502)
        self.assertNotIn("ollama", response.text.lower())

    def test_health_reports_ollama_state_without_leaking_details(self):
        class Broken(FakeOllama):
            async def get(self, url):
                raise RuntimeError("detalle interno")

        with patch.object(main.httpx, "AsyncClient", FakeOllama):
            self.assertEqual(self.alice.get("/api/health").json()["ollama"], "connected")

        with patch.object(main.httpx, "AsyncClient", Broken):
            response = self.alice.get("/api/health")
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("detalle", response.text)


if __name__ == "__main__":
    unittest.main()
