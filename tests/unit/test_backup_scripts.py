"""Copias de seguridad (BACKUP_RESTORE.md): el helper que corre en el contenedor y las garantías
estáticas de los scripts de PowerShell. La prueba completa con Docker es
scripts/test_backup_restore.ps1 (resultado en BACKUP_RESTORE.md)."""

import base64
import importlib.util
import json
import re
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
_spec = importlib.util.spec_from_file_location(
    "nexaro_backup_helper", SCRIPTS / "backup" / "nexaro_backup_helper.py"
)
assert _spec is not None and _spec.loader is not None
helper = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(helper)

PS_SCRIPTS = [
    SCRIPTS / "backup_nexaro.ps1",
    SCRIPTS / "restore_nexaro.ps1",
    SCRIPTS / "verify_backup.ps1",
    SCRIPTS / "register_backup_task.ps1",
    SCRIPTS / "test_backup_restore.ps1",
    SCRIPTS / "backup" / "common.ps1",
    SCRIPTS / "remote_access.ps1",
    SCRIPTS / "smoke_isolated.ps1",
]


def _live_db(path: Path) -> sqlite3.Connection:
    db = sqlite3.connect(path)
    db.execute("PRAGMA journal_mode = WAL")
    db.execute("CREATE TABLE users (id TEXT PRIMARY KEY)")
    db.execute("CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, name TEXT)")
    db.execute("INSERT INTO schema_migrations VALUES (1, 'baseline'), (2, 'platform')")
    db.executemany("INSERT INTO users VALUES (?)", [(f"u{i}",) for i in range(50)])
    db.commit()
    return db


def test_snapshot_is_consistent_while_a_writer_holds_uncommitted_changes(tmp_path: Path) -> None:
    live = _live_db(tmp_path / "nexaro.db")
    live.execute("BEGIN IMMEDIATE")
    live.execute("INSERT INTO users VALUES ('sin-confirmar')")
    report = helper.snapshot(tmp_path / "nexaro.db", tmp_path / "copia.db")
    live.rollback()
    live.close()
    assert report["integrity"] == "ok"
    assert report["counts"]["users"] == 50  # lo no confirmado no entra en la copia
    assert report["schema_version"] == 2
    copy = sqlite3.connect(tmp_path / "copia.db")
    assert copy.execute("PRAGMA journal_mode").fetchone()[0] == "delete"  # archivo autónomo
    copy.close()


def test_snapshot_never_overwrites_and_leaves_the_source_untouched(tmp_path: Path) -> None:
    _live_db(tmp_path / "nexaro.db").close()
    source_bytes = (tmp_path / "nexaro.db").read_bytes()
    (tmp_path / "copia.db").write_bytes(b"copia anterior")
    with pytest.raises(SystemExit, match="ya existe"):
        helper.snapshot(tmp_path / "nexaro.db", tmp_path / "copia.db")
    assert (tmp_path / "copia.db").read_bytes() == b"copia anterior"
    assert (tmp_path / "nexaro.db").read_bytes() == source_bytes


def test_inspect_detects_a_corrupted_copy(tmp_path: Path) -> None:
    _live_db(tmp_path / "nexaro.db").close()
    helper.snapshot(tmp_path / "nexaro.db", tmp_path / "copia.db")
    data = bytearray((tmp_path / "copia.db").read_bytes())
    for page in (1, 2):  # cabeceras b-tree de las páginas de las tablas (tras la página 0)
        data[4096 * page : 4096 * page + 12] = b"\xff" * 12
    (tmp_path / "copia.db").write_bytes(bytes(data))
    try:
        report = helper.inspect(tmp_path / "copia.db", immutable=True)
        assert report["integrity"] != "ok"
    except sqlite3.DatabaseError:
        pass  # también es una detección: la copia no se puede usar


def test_remove_only_deletes_its_own_temporary_snapshots(tmp_path: Path) -> None:
    live = tmp_path / "nexaro.db"
    live.write_bytes(b"base viva")
    with pytest.raises(SystemExit, match="se niega"):
        helper.main(["remove", str(live)])
    assert live.exists()
    temp = tmp_path / ".nexaro-backup-20261123-030000.db"
    temp.write_bytes(b"x")
    assert helper.main(["remove", str(temp)]) == 0 and not temp.exists()


def test_status_write_is_atomic_json(tmp_path: Path) -> None:
    payload = base64.b64encode(json.dumps({"ok": True, "name": "ñ"}).encode()).decode()
    assert helper.main(["status-write", str(tmp_path / "s.json"), payload]) == 0
    assert json.loads((tmp_path / "s.json").read_text(encoding="utf-8")) == {
        "name": "ñ",
        "ok": True,
    }


def test_helper_is_ascii_so_powershell_can_pipe_it() -> None:
    (SCRIPTS / "backup" / "nexaro_backup_helper.py").read_bytes().decode("ascii")


def test_helper_cli_runs_with_the_standard_library_only(tmp_path: Path) -> None:
    _live_db(tmp_path / "nexaro.db").close()
    proc = subprocess.run(  # noqa: S603
        [
            sys.executable,
            "-I",
            str(SCRIPTS / "backup" / "nexaro_backup_helper.py"),
            "inspect",
            str(tmp_path / "nexaro.db"),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["counts"]["users"] == 50


@pytest.mark.parametrize("script", PS_SCRIPTS, ids=lambda p: p.name)
def test_powershell_scripts_are_never_destructive(script: Path) -> None:
    raw = script.read_text(encoding="utf-8-sig")
    # Solo el código: los comentarios explican precisamente lo que NO se hace.
    text = "\n".join(line for line in raw.splitlines() if not line.lstrip().startswith("#"))
    assert not re.search(r"compose\s+down", text)
    assert "--volumes" not in text and " prune" not in text
    if script.name not in ("test_backup_restore.ps1", "smoke_isolated.ps1"):
        assert "volume rm" not in text  # solo las pruebas borran SUS volúmenes temporales
    assert script.read_bytes().startswith(b"\xef\xbb\xbf")  # UTF-8 con BOM: PowerShell 5.1


@pytest.mark.parametrize(
    ("name", "prefix"),
    [("test_backup_restore.ps1", "nexaro-bkptest-*"), ("smoke_isolated.ps1", "nexaro-smoke-*")],
)
def test_only_the_tests_remove_volumes_and_only_their_own_labelled_ones(
    name: str, prefix: str
) -> None:
    text = (SCRIPTS / name).read_text(encoding="utf-8-sig")
    assert 'docker volume ls -q --filter "label=nexaro.test=$run"' in text
    assert f"if ($v -like '{prefix}')" in text
    assert (
        "nexaro-personal-ai_nexaro_data" not in text.split(".DESCRIPTION", 1)[1].split("#>", 1)[1]
    )


def test_backups_refuse_a_destination_inside_the_repository() -> None:
    common = (SCRIPTS / "backup" / "common.ps1").read_text(encoding="utf-8-sig")
    backup = (SCRIPTS / "backup_nexaro.ps1").read_text(encoding="utf-8-sig")
    assert "function Assert-OutsideRepo" in common and "Assert-OutsideRepo $BackupRoot" in backup


def test_restore_defaults_to_a_new_volume_and_guards_the_live_one() -> None:
    text = (SCRIPTS / "restore_nexaro.ps1").read_text(encoding="utf-8-sig")
    assert "nexaro-restore-$stamp" in text
    assert "-Yes no se admite para el volumen real" in text
    assert "Reason pre-restore" in text  # copia del estado actual antes de sustituirlo
    assert "os.replace(db, '/data/nexaro.replaced-" in text  # la base anterior no se borra


def test_scheduled_task_is_a_dry_run_unless_asked() -> None:
    text = (SCRIPTS / "register_backup_task.ps1").read_text(encoding="utf-8-sig")
    assert text.index("if (-not $Register)") < text.index("Register-ScheduledTask")


@pytest.mark.skipif(shutil.which("pwsh") is None, reason="sin PowerShell 7")
@pytest.mark.parametrize("script", PS_SCRIPTS, ids=lambda p: p.name)
def test_powershell_scripts_parse(script: Path) -> None:
    command = (
        "$e=$null; [void][System.Management.Automation.Language.Parser]::ParseFile("
        f"'{script}',[ref]$null,[ref]$e); "
        "if ($e) { $e | ForEach-Object { $_.Message }; exit 1 }"
    )
    proc = subprocess.run(  # noqa: S603
        [shutil.which("pwsh") or "pwsh", "-NoProfile", "-NonInteractive", "-Command", command],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_remote_access_never_uses_funnel_and_needs_apply() -> None:
    text = (SCRIPTS / "remote_access.ps1").read_text(encoding="utf-8-sig")
    code = "\n".join(ln for ln in text.splitlines() if not ln.lstrip().startswith("#"))
    # El script nunca EJECUTA funnel (solo lo detecta y aconseja desactivarlo).
    assert not re.search(r"&\s*\$ts\s+funnel", code)
    assert "if (-not $Apply)" in code
    assert code.index("if (-not $Apply)") < code.index("& $ts serve --bg")
    assert "127.0.0.1:$LocalPort" in code  # se publica el puerto de loopback, nunca 0.0.0.0


def test_cold_snapshot_of_a_cleanly_closed_wal_database_creates_no_side_files(
    tmp_path: Path,
) -> None:
    """Regresión (copia real del 2026-11-23): con el backend parado la base WAL no tiene -shm y en
    un volumen de solo lectura SQLite no puede crearlo. En modo inmutable no se crea nada junto
    al origen."""
    _live_db(tmp_path / "nexaro.db").close()
    assert not (tmp_path / "nexaro.db-shm").exists()
    report = helper.snapshot(tmp_path / "nexaro.db", tmp_path / "copia.db", source_immutable=True)
    assert report["integrity"] == "ok" and report["counts"]["users"] == 50
    assert not (tmp_path / "nexaro.db-shm").exists()
    assert not (tmp_path / "nexaro.db-wal").exists()


def test_cold_backups_use_immutable_mode_only_on_the_read_only_volume() -> None:
    text = (SCRIPTS / "backup_nexaro.ps1").read_text(encoding="utf-8-sig")
    assert "'/backup/nexaro.db', '--immutable')" in text
    assert '"${Volume}:/data:ro"' in text  # el modo inmutable solo con el volumen en solo lectura
    hot = text.split("if ($running) {", 1)[1].split("} else {", 1)[0]
    assert "--immutable" not in hot  # con la app en marcha, nunca


@pytest.mark.skipif(shutil.which("pwsh") is None, reason="sin PowerShell 7")
@pytest.mark.parametrize(("image_exists", "expected"), [(True, "sha256:viva"), (False, "respaldo")])
def test_backups_fall_back_when_the_running_container_image_is_gone(
    image_exists: bool, expected: str
) -> None:
    """Regresión (2026-11-23): el contenedor seguía en marcha pero su imagen ya no existía y la
    copia fallaba («No such image»). Docker se sustituye por una función."""
    inspect_code = 0 if image_exists else 1
    command = (
        f". '{SCRIPTS / 'backup' / 'common.ps1'}'; "
        "function docker { "
        f"if ($args[0] -eq 'image') {{ $global:LASTEXITCODE = {inspect_code} }} "
        "else { $global:LASTEXITCODE = 0; if ($args[0] -eq 'inspect') { 'sha256:viva' } } }; "
        "Get-ContainerImage 'nexaro-backend' 'respaldo'"
    )
    proc = subprocess.run(  # noqa: S603
        [shutil.which("pwsh") or "pwsh", "-NoProfile", "-NonInteractive", "-Command", command],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert proc.stdout.strip() == expected
