"""Helper of the NEXARO backup scripts (BACKUP_RESTORE.md). Standard library only.

It runs INSIDE a container of the backend image (the PowerShell scripts pipe it through stdin with
`docker exec -i ... python - <command>` or `docker run -i ... python - <command>`), so the Windows
host needs neither Python nor sqlite3. It can also be imported by the tests.

    snapshot SRC DST [--immutable]  consistent copy (SQLite backup API; safe with the app running);
                              --immutable ONLY with the backend stopped and the volume read-only
    inspect PATH [--immutable] JSON: integrity, foreign keys, schema version and row counts
    status-write PATH B64     writes the backup status (base64-encoded JSON) for the ops panel
    remove PATH               deletes a temporary snapshot created by `snapshot` (name-checked)

It never modifies SRC: `snapshot` only reads it; `inspect --immutable` opens the file read-only and
without locks (only for copies or for a database nobody is writing to).
"""

from __future__ import annotations

import base64
import json
import os
import sqlite3
import sys
from pathlib import Path
from typing import Any

COUNTED_TABLES = (
    "users",
    "sessions",
    "conversations",
    "messages",
    "organizations",
    "memberships",
    "documents",
    "document_chunks",
    "api_keys",
    "expenses",
    "audit_events",
)


def snapshot(source: Path, destination: Path, *, source_immutable: bool = False) -> dict[str, Any]:
    """Online copy (sqlite3 backup API). Refuses to overwrite an existing destination.

    source_immutable: ONLY when nobody can be writing (backend stopped, volume mounted read-only).
    A WAL database closed cleanly has no -shm file and SQLite cannot create one on a read-only
    mount ("unable to open database file"); immutable mode reads the file as-is, without locks.
    """
    if not source.is_file():
        raise SystemExit(f"no existe la base de datos {source}")
    if destination.exists():
        raise SystemExit(f"el destino ya existe: {destination}")
    flags = "mode=ro&immutable=1" if source_immutable else "mode=ro"
    src = sqlite3.connect(f"file:{source.as_posix()}?{flags}", uri=True, timeout=30)
    try:
        dst = sqlite3.connect(destination)
        try:
            src.backup(dst)
            # The copy is a standalone file: no WAL that could be lost when copying it.
            dst.execute("PRAGMA journal_mode = DELETE")
        finally:
            dst.close()
    finally:
        src.close()
    return inspect(destination, immutable=True)


def inspect(path: Path, *, immutable: bool = False) -> dict[str, Any]:
    if not path.is_file():
        raise SystemExit(f"no existe {path}")
    flags = "mode=ro&immutable=1" if immutable else "mode=ro"
    db = sqlite3.connect(f"file:{path.as_posix()}?{flags}", uri=True, timeout=30)
    try:
        integrity = [row[0] for row in db.execute("PRAGMA integrity_check")]
        fk_errors = len(db.execute("PRAGMA foreign_key_check").fetchall())
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        version = None
        migrations: list[str] = []
        if "schema_migrations" in tables:
            rows = db.execute("SELECT version, name FROM schema_migrations ORDER BY version")
            migrations = [f"{v}:{n}" for v, n in rows]
            version = int(migrations[-1].split(":", 1)[0]) if migrations else None
        counts = {
            table: db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]  # noqa: S608  # nosec B608 - fixed table names
            for table in COUNTED_TABLES
            if table in tables
        }
    finally:
        db.close()
    return {
        "integrity": "ok" if integrity == ["ok"] else "; ".join(integrity[:5]),
        "foreign_key_errors": fk_errors,
        "schema_version": version,
        "migrations": migrations,
        "counts": counts,
        "size_bytes": path.stat().st_size,
    }


def status_write(path: Path, payload_b64: str) -> None:
    # Base64: PowerShell 5.1 mangles double quotes in arguments to native programs.
    data = json.loads(base64.b64decode(payload_b64).decode("utf-8"))
    if not isinstance(data, dict):
        raise SystemExit("el estado debe ser un objeto JSON")
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    os.replace(tmp, path)


def main(argv: list[str]) -> int:
    if len(argv) >= 3 and argv[0] == "snapshot":
        immutable = "--immutable" in argv[3:]
        report = snapshot(Path(argv[1]), Path(argv[2]), source_immutable=immutable)
        print(json.dumps(report, sort_keys=True))
        return 0
    if len(argv) >= 2 and argv[0] == "inspect":
        report = inspect(Path(argv[1]), immutable="--immutable" in argv[2:])
        print(json.dumps(report, sort_keys=True))
        return 0 if report["integrity"] == "ok" and report["foreign_key_errors"] == 0 else 1
    if len(argv) == 3 and argv[0] == "status-write":
        status_write(Path(argv[1]), argv[2])
        return 0
    if len(argv) == 2 and argv[0] == "remove":
        target = Path(argv[1])
        # Only the temporary copies this helper is asked to create; never the live database.
        if not target.name.startswith(".nexaro-backup-") or not target.name.endswith(".db"):
            raise SystemExit(f"se niega a borrar {target}")
        target.unlink(missing_ok=True)
        return 0
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
