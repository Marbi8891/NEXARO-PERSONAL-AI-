"""Errores de botocore traducidos al vocabulario del gateway (Bedrock y SageMaker)."""

from botocore.exceptions import BotoCoreError, ClientError, ReadTimeoutError
from botocore.exceptions import ConnectionError as BotoConnectionError

from ai_gateway.errors import ProviderError, ProviderTimeoutError, ProviderUnavailableError

_UNAVAILABLE = {
    "ThrottlingException",
    "ServiceUnavailableException",
    "InternalServerException",
    "ModelNotReadyException",
    "ServiceUnavailable",
    "ModelError",
}
_TIMEOUT = {"ModelTimeoutException"}


def translate(exc: Exception, service: str) -> ProviderError:
    """Mensajes genéricos: el detalle de AWS (ARNs, cuenta) no debe llegar al cliente."""
    if isinstance(exc, ClientError):
        code = exc.response.get("Error", {}).get("Code", "")
        if code in _TIMEOUT:
            return ProviderTimeoutError(f"{service} agotó el tiempo de espera")
        if code in _UNAVAILABLE:
            return ProviderUnavailableError(f"{service} no disponible ({code})")
        return ProviderError(f"{service} rechazó la solicitud ({code})")
    if isinstance(exc, ReadTimeoutError):
        return ProviderTimeoutError(f"{service} agotó el tiempo de espera")
    if isinstance(exc, (BotoConnectionError, BotoCoreError)):
        return ProviderUnavailableError(f"{service} no disponible")
    return ProviderError(f"Respuesta no válida de {service}")
