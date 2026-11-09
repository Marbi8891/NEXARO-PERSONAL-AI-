from dataclasses import dataclass


@dataclass(frozen=True)
class GatewayPolicy:
    """Límites que el gateway aplica a toda solicitud, sea cual sea el proveedor.

    La nube está desactivada por defecto: los datos no salen de la máquina salvo decisión
    explícita de configuración.
    """

    max_input_chars: int = 32_000
    max_output_tokens: int = 2_048
    timeout_seconds: float = 180.0
    max_retries: int = 1  # solo ante indisponibilidad; un timeout no se reintenta
    retry_backoff_seconds: float = 0.5
    allow_cloud: bool = False
    breaker_threshold: int = 3  # fallos de disponibilidad seguidos que abren el cortacircuitos
    breaker_cooldown_seconds: float = 30.0
    cloud_monthly_budget_usd: float | None = None
