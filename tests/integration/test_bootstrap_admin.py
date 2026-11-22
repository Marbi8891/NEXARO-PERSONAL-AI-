import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from tests.legacy_db import LEGACY_EMAIL, create_legacy_database

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    path = tmp_path / "nexaro.db"
    create_legacy_database(path)
    return path


def run_cli(db_path: Path, *extra: str, confirm: str | None = None, env_email: str | None = None):
    env = {
        **os.environ,
        "DATABASE_PATH": str(db_path),
        "PYTHONPATH": os.pathsep.join(str(ROOT / p) for p in ("packages", "apps/api", ".")),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    env.pop("ADMIN_EMAIL", None)
    if env_email:
        env["ADMIN_EMAIL"] = env_email
    return subprocess.run(  # noqa: S603 - argumentos fijos de prueba
        [
            sys.executable,
            "-B",
            "-m",
            "nexaro_api.bootstrap_admin",
            "--confirm-database",
            confirm or str(db_path),
            *extra,
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        input="",
        timeout=60,
        check=False,
    )


def user_row(db_path: Path) -> sqlite3.Row | None:
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    try:
        if "role" not in [r[1] for r in connection.execute("PRAGMA table_info(users)")]:
            return None
        return connection.execute(
            "SELECT role, is_active, approval_status, password_hash FROM users"
        ).fetchone()
    finally:
        connection.close()


def test_existing_account_is_untouched_without_explicit_flag(db_path: Path) -> None:
    result = run_cli(db_path, "--email", LEGACY_EMAIL)
    assert result.returncode != 0
    assert "--promote-existing" in result.stdout + result.stderr
    assert user_row(db_path) is None, "no debe migrar ni modificar nada"
    assert list(db_path.parent.glob("*.pre-admin-*")) == []


def test_email_is_required_and_not_hardcoded(db_path: Path) -> None:
    assert run_cli(db_path).returncode != 0
    assert user_row(db_path) is None


def test_promote_existing_keeps_password_and_data(db_path: Path) -> None:
    connection = sqlite3.connect(db_path)
    before = connection.execute("SELECT password_hash FROM users").fetchone()[0]
    connection.close()

    result = run_cli(db_path, "--promote-existing", env_email=LEGACY_EMAIL)
    assert result.returncode == 0, result.stdout + result.stderr

    row = user_row(db_path)
    assert row is not None
    assert (row["role"], row["is_active"], row["approval_status"]) == ("admin", 1, "approved")
    assert row["password_hash"] == before
    assert len(list(db_path.parent.glob("*.pre-admin-*"))) == 1

    connection = sqlite3.connect(db_path)
    try:
        assert connection.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 4
        assert connection.execute("SELECT COUNT(*) FROM messages").fetchone()[0] == 52
    finally:
        connection.close()


def test_wrong_confirmation_path_changes_nothing(db_path: Path) -> None:
    result = run_cli(
        db_path, "--email", LEGACY_EMAIL, "--promote-existing", confirm=str(db_path) + ".otra"
    )
    assert result.returncode != 0
    assert user_row(db_path) is None
