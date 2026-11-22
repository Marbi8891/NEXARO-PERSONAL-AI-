"""Migraciones versionadas para SQLite (ADR-0005).

Todo el lote pendiente se aplica en una sola transacción de escritura: si algo falla, no queda
nada a medias. Las migraciones aplicadas no se editan (se verifica su checksum).
"""

import hashlib
import sqlite3
import uuid
from collections.abc import Callable
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from nexaro_core.database.connection import Database, begin_write

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


class MigrationError(Exception):
    pass


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    apply: Callable[[sqlite3.Connection], None]
    checksum: str


def split_statements(script: str) -> list[str]:
    """Divide un script SQL respetando comillas, comentarios y bloques de trigger."""
    statements: list[str] = []
    buffer = ""
    for line in script.splitlines(keepends=True):
        buffer += line
        if sqlite3.complete_statement(buffer):
            if buffer.strip():
                statements.append(buffer.strip())
            buffer = ""
    if buffer.strip() and not all(
        part.strip().startswith("--") or not part.strip() for part in buffer.splitlines()
    ):
        raise MigrationError("El script termina con una sentencia incompleta")
    return statements


def sql_migration(version: int, name: str, path: Path) -> Migration:
    text = path.read_text(encoding="utf-8")
    statements = split_statements(text)

    def apply(db: sqlite3.Connection) -> None:
        for statement in statements:
            db.execute(statement)

    return Migration(version, name, apply, hashlib.sha256(text.encode()).hexdigest())


def platform_migrations() -> list[Migration]:
    """Migraciones de la plataforma (organizaciones, documentos, agentes...). La 1 es la línea
    base y la aporta la raíz de composición, que conoce los módulos de producto."""
    return [
        sql_migration(2, "platform", MIGRATIONS_DIR / "sqlite" / "0002_platform.sql"),
        sql_migration(3, "api_keys", MIGRATIONS_DIR / "sqlite" / "0003_api_keys.sql"),
        sql_migration(4, "api_key_scopes", MIGRATIONS_DIR / "sqlite" / "0004_api_key_scopes.sql"),
        sql_migration(5, "expenses", MIGRATIONS_DIR / "sqlite" / "0005_expenses.sql"),
        sql_migration(
            6, "inference_metrics", MIGRATIONS_DIR / "sqlite" / "0006_inference_metrics.sql"
        ),
        sql_migration(7, "message_agent", MIGRATIONS_DIR / "sqlite" / "0007_message_agent.sql"),
    ]


def pending_versions(database: Database, migrations: list[Migration]) -> list[int]:
    """Versiones que `run_migrations` aplicaría, sin escribir nada en la base."""
    if not database.path.is_file():
        return [m.version for m in migrations]
    with closing(sqlite3.connect(database.path)) as db:
        tracked = db.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'schema_migrations'"
        ).fetchone()
        applied = (
            {row[0] for row in db.execute("SELECT version FROM schema_migrations")}
            if tracked
            else set()
        )
    return [m.version for m in migrations if m.version not in applied]


def backup_before_migrations(
    database: Database, migrations: list[Migration], now: datetime | None = None
) -> Path | None:
    """Copia la base junto a ella antes de aplicar migraciones pendientes sobre datos existentes.

    No hace nada si la base no existe, está vacía o no hay nada pendiente. La copia usa la API
    de backup de SQLite (coherente aunque haya WAL) y se comprueba con `integrity_check`; si la
    copia no es válida se aborta y no se migra. Nunca se borran copias anteriores.
    """
    path = database.path
    if not path.is_file() or path.stat().st_size == 0:
        return None
    with closing(sqlite3.connect(path)) as db:
        has_tables = db.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        ).fetchone()
    if not has_tables:
        return None
    pending = pending_versions(database, migrations)
    if not pending:
        return None

    stamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%S%fZ")
    # El UUID evita colisiones entre procesos que arrancan al mismo tiempo.
    target = path.with_name(
        f"{path.stem}.pre-migration-v{pending[0]}-{stamp}-{uuid.uuid4().hex[:8]}{path.suffix}"
    )
    try:
        # Creación exclusiva: nunca sobrescribir una copia preexistente.
        target.touch(exist_ok=False)
        with closing(sqlite3.connect(path)) as source, closing(sqlite3.connect(target)) as copy:
            source.backup(copy)
            result = copy.execute("PRAGMA integrity_check").fetchone()[0]
        if result != "ok":
            raise MigrationError(f"La copia {target.name} no supera integrity_check: {result}")
        return target
    except Exception:
        # No dejar una copia parcial si el backup o su validación fallan.
        target.unlink(missing_ok=True)
        raise


def run_migrations(database: Database, migrations: list[Migration]) -> list[int]:
    """Aplica las pendientes y devuelve sus versiones."""
    versions = [m.version for m in migrations]
    if versions != list(range(1, len(migrations) + 1)):
        raise MigrationError("Las versiones deben ser 1..N, sin huecos ni duplicados")

    applied_now: list[int] = []
    with database.connect() as db:
        begin_write(db)
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                checksum TEXT NOT NULL,
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        applied = {
            row["version"]: row["checksum"]
            for row in db.execute("SELECT version, checksum FROM schema_migrations")
        }
        known = {m.version: m for m in migrations}

        newer = set(applied) - known.keys()
        if newer:
            raise MigrationError(
                f"La base tiene migraciones desconocidas {sorted(newer)}: el código es más antiguo"
            )
        for version, checksum in applied.items():
            if known[version].checksum != checksum:
                raise MigrationError(f"La migración {version} aplicada fue modificada")

        for migration in migrations:
            if migration.version in applied:
                continue
            migration.apply(db)
            db.execute(
                "INSERT INTO schema_migrations (version, name, checksum) VALUES (?, ?, ?)",
                (migration.version, migration.name, migration.checksum),
            )
            applied_now.append(migration.version)
    return applied_now
