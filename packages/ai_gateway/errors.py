class ProviderError(Exception):
    """Fallo al consultar un proveedor de IA. El mensaje no debe exponerse al cliente."""


class ProviderTimeoutError(ProviderError):
    pass


class ProviderUnavailableError(ProviderError):
    pass


class PolicyError(Exception):
    """La política del gateway rechaza la solicitud (no es un fallo del proveedor)."""
