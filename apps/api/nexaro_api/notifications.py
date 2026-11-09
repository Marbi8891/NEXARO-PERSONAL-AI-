"""Avisos derivados del estado real del sistema. No se persisten: se recalculan en cada consulta.

Cada aviso tiene un id estable (el cliente puede recordar los descartados) y nunca incluye
correos, IPs ni contenido de mensajes.
"""

from typing import Any

FAILED_LOGIN_THRESHOLD = 5
FAILED_LOGIN_WINDOW_MINUTES = 60


def build_notifications(
    *,
    model_available: bool,
    is_admin: bool,
    pending_approvals: int = 0,
    failed_logins: int = 0,
    registration_open: bool = False,
) -> list[dict[str, Any]]:
    notes: list[dict[str, Any]] = []
    if not model_available:
        notes.append(
            {
                "id": "model-unavailable",
                "severity": "error",
                "title": "El modelo de IA no está disponible",
                "text": "El chat no responderá hasta que el servicio se recupere.",
                "href": None,
            }
        )
    if not is_admin:
        return notes
    if pending_approvals:
        many = pending_approvals != 1
        noun = "solicitudes de acceso pendientes" if many else "solicitud de acceso pendiente"
        notes.append(
            {
                "id": "pending-approvals",
                "severity": "warning",
                "title": f"{pending_approvals} {noun}",
                "text": "Revísalas en Administración.",
                "href": "#/admin",
            }
        )
    if failed_logins >= FAILED_LOGIN_THRESHOLD:
        notes.append(
            {
                "id": "failed-logins",
                "severity": "warning",
                "title": f"{failed_logins} intentos de acceso fallidos en la última hora",
                "text": "Consulta la auditoría por si fuese un ataque de fuerza bruta.",
                "href": "#/admin",
            }
        )
    if registration_open:
        notes.append(
            {
                "id": "registration-open",
                "severity": "info",
                "title": "El registro público está abierto",
                "text": "Cualquiera puede solicitar acceso (requiere tu aprobación).",
                "href": "#/admin",
            }
        )
    return notes
