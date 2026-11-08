import argparse
import getpass
import os
import re
import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path

from nexaro_api.bootstrap import migrate
from nexaro_core.config import get_settings
from nexaro_core.database import Database
from nexaro_core.identity import approve_user, set_user_role
from nexaro_core.security import hash_password


def create_backup(database_path: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = database_path.with_name(
        f"{database_path.stem}.pre-admin-{stamp}{database_path.suffix}"
    )

    if backup_path.exists():
        raise RuntimeError("Ya existe el archivo de backup.")

    with (
        closing(sqlite3.connect(database_path)) as source,
        closing(sqlite3.connect(backup_path)) as destination,
    ):
        source.backup(destination)

    return backup_path


def find_user_id(database_path: Path, email: str) -> str | None:
    """Consulta de solo lectura: devuelve el id de la cuenta o None."""
    uri = f"file:{database_path}?mode=ro"

    with closing(sqlite3.connect(uri, uri=True)) as connection:
        try:
            row = connection.execute(
                "SELECT id FROM users WHERE email = ? COLLATE NOCASE",
                (email,),
            ).fetchone()
        except sqlite3.OperationalError:
            return None

    return row[0] if row else None


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Alta inicial y segura del administrador de NEXARO."
    )
    parser.add_argument(
        "--confirm-database",
        required=True,
        help="Ruta exacta de la base de datos que se autoriza modificar.",
    )
    parser.add_argument(
        "--email",
        help="Correo del administrador. Si se omite, se usa ADMIN_EMAIL.",
    )
    parser.add_argument(
        "--promote-existing",
        action="store_true",
        help=(
            "Si la cuenta ya existe, la convierte en administrador "
            "(activa y aprobada) sin cambiar su contraseña."
        ),
    )
    parser.add_argument(
        "--assign-orphaned-conversations",
        action="store_true",
        help="Autoriza asignar al administrador las conversaciones sin propietario.",
    )
    args = parser.parse_args()

    admin_email = (args.email or os.getenv("ADMIN_EMAIL") or "").strip().lower()

    if not admin_email:
        raise SystemExit(
            "ERROR: indica el correo con --email o la variable ADMIN_EMAIL. "
            "No se ha modificado nada."
        )

    database_path = get_settings().database_path.expanduser().resolve()
    confirmed_path = Path(args.confirm_database).expanduser().resolve()

    if database_path != confirmed_path:
        raise SystemExit(
            "ERROR: la ruta confirmada no coincide con DATABASE_PATH. No se ha modificado nada."
        )

    if not database_path.is_file():
        raise SystemExit("No existe la base de datos. No se ha modificado nada.")

    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", admin_email):
        raise SystemExit("La dirección de correo no es válida.")

    existing_id = find_user_id(database_path, admin_email)

    if existing_id and not args.promote_existing:
        raise SystemExit(
            "La cuenta ya existe. No se ha cambiado ningún usuario. "
            "Usa --promote-existing para convertirla en administrador."
        )

    print("NEXARO - Alta inicial del administrador")
    print("Base de datos:", database_path)
    print("Correo:", admin_email)
    print("Modo:", "promover cuenta existente" if existing_id else "crear cuenta")

    password_hash = None

    if not existing_id:
        password = getpass.getpass("Nueva contraseña (mínimo 12 caracteres): ")
        confirmation = getpass.getpass("Repite la contraseña: ")

        if password != confirmation:
            raise SystemExit("Las contraseñas no coinciden.")

        try:
            password_hash = hash_password(password)
        except ValueError as exc:
            raise SystemExit(str(exc)) from None

    backup_path = create_backup(database_path)
    print("Copia de seguridad creada:", backup_path)

    migrate(Database(database_path))  # esquema al día, en su propia transacción atómica

    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")

    try:
        with connection:
            connection.execute("BEGIN IMMEDIATE")

            current = connection.execute(
                "SELECT id FROM users WHERE email = ? COLLATE NOCASE",
                (admin_email,),
            ).fetchone()

            if current and not args.promote_existing:
                raise RuntimeError("La cuenta ya existe. No se ha cambiado ningún usuario.")

            if current:
                admin_id = current["id"]
                approve_user(connection, admin_id)
                set_user_role(connection, admin_id, "admin")
            else:
                if password_hash is None:
                    raise RuntimeError("La cuenta ha desaparecido durante la operación.")

                connection.execute(
                    """
                    INSERT INTO users (
                        id,
                        email,
                        password_hash,
                        role,
                        is_active,
                        approval_status
                    )
                    VALUES (
                        lower(hex(randomblob(16))),
                        ?,
                        ?,
                        'admin',
                        1,
                        'approved'
                    )
                    """,
                    (admin_email, password_hash),
                )

                admin_id = connection.execute(
                    "SELECT id FROM users WHERE email = ? COLLATE NOCASE",
                    (admin_email,),
                ).fetchone()["id"]

            assigned = 0

            if args.assign_orphaned_conversations:
                result = connection.execute(
                    """
                    UPDATE conversations
                    SET user_id = ?
                    WHERE user_id IS NULL
                    """,
                    (admin_id,),
                )
                assigned = result.rowcount

        print(
            "Cuenta promovida a administrador."
            if current
            else "Administrador creado correctamente."
        )
        print("Rol: admin")
        print("Cuenta activa: sí")
        print("Aprobación: approved")
        print("Conversaciones asignadas:", assigned)

    finally:
        connection.close()


if __name__ == "__main__":
    main()
