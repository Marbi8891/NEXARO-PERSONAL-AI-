import hashlib
import secrets


def create_session_token() -> str:
    return secrets.token_urlsafe(32)


def hash_session_token(token: str) -> str:
    """Solo se persiste el SHA-256: una fuga de la base no permite suplantar sesiones."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
