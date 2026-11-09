import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

BUSY_TIMEOUT_SECONDS = 10.0


class Database:
    """Acceso a SQLite. `connect()` confirma al salir y revierte ante cualquier excepción."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def ensure_parent(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=BUSY_TIMEOUT_SECONDS)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        # WAL: lectores y un escritor no se bloquean entre sí (ADR-0015). El modo se guarda en
        # el fichero; repetirlo es barato y no hace nada si ya está activo.
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = NORMAL")
        try:
            with connection:
                yield connection
        finally:
            connection.close()


def begin_write(db: sqlite3.Connection) -> None:
    """Abre una transacción de escritura explícita.

    sqlite3 no abre transacción antes de un DDL; sin esto, un fallo a mitad de una migración
    dejaría el esquema a medias. También evita carreras en comprobar-y-actualizar.
    """
    db.execute("BEGIN IMMEDIATE")
