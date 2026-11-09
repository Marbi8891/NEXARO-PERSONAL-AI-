"""Configuración centralizada y validada. Única fuente de lectura de variables de entorno."""

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

KNOWN_PROVIDERS = frozenset({"ollama", "bedrock", "sagemaker"})
CLOUD_PROVIDERS = frozenset({"bedrock", "sagemaker"})
DEFAULT_ORIGINS = frozenset({"http://127.0.0.1:8001", "http://localhost:8001"})


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore", populate_by_name=True, frozen=True)

    environment: Literal["development", "staging", "production"] = Field(
        default="development", alias="NEXARO_ENV"
    )
    database_path: Path = Field(default=Path("/data/nexaro.db"), alias="DATABASE_PATH")
    frontend_path: Path = Field(default=Path("/app/frontend"), alias="FRONTEND_PATH")

    ollama_base_url: str = Field(default="http://localhost:11434", alias="OLLAMA_BASE_URL")
    ollama_model: str = Field(default="qwen2.5:3b", alias="OLLAMA_MODEL")
    # Rendimiento de Ollama. num_ctx debe ser constante entre peticiones
    # (si cambia, Ollama recarga el modelo).
    ollama_keep_alive: str = Field(default="30m", alias="OLLAMA_KEEP_ALIVE")
    ollama_num_ctx: int | None = Field(default=4096, gt=0, alias="OLLAMA_NUM_CTX")
    ollama_num_thread: int | None = Field(default=None, gt=0, alias="OLLAMA_NUM_THREAD")
    # Tope de tokens de salida según el tipo de consulta (heurística sin medir; ver ADR-0014).
    output_tokens_short: int = Field(default=512, gt=0, alias="OUTPUT_TOKENS_SHORT")
    output_tokens_default: int = Field(default=1024, gt=0, alias="OUTPUT_TOKENS_DEFAULT")
    output_tokens_code: int = Field(default=2048, gt=0, alias="OUTPUT_TOKENS_CODE")
    chat_history_max_chars: int = Field(default=8000, gt=0, alias="CHAT_HISTORY_MAX_CHARS")

    # AI Gateway. Nube desactivada por defecto; activarla exige región, presupuesto y precios.
    ai_provider_order: Annotated[tuple[str, ...], NoDecode] = Field(
        default=("ollama",), alias="AI_PROVIDER_ORDER"
    )
    ai_allow_cloud: bool = Field(default=False, alias="AI_ALLOW_CLOUD")
    ai_max_output_tokens: int = Field(default=2048, gt=0, alias="AI_MAX_OUTPUT_TOKENS")
    ai_max_input_chars: int = Field(default=32_000, gt=0, alias="AI_MAX_INPUT_CHARS")
    ai_timeout_seconds: float = Field(default=180.0, gt=0, alias="AI_TIMEOUT_SECONDS")
    ai_max_retries: int = Field(default=1, ge=0, le=3, alias="AI_MAX_RETRIES")
    ai_cloud_monthly_budget_usd: float | None = Field(
        default=None, gt=0, alias="AI_CLOUD_MONTHLY_BUDGET_USD"
    )
    aws_region: str | None = Field(default=None, alias="AWS_REGION")
    bedrock_model_id: str | None = Field(default=None, alias="BEDROCK_MODEL_ID")
    bedrock_price_input_per_1k: float | None = Field(
        default=None, ge=0, alias="BEDROCK_PRICE_INPUT_PER_1K"
    )
    bedrock_price_output_per_1k: float | None = Field(
        default=None, ge=0, alias="BEDROCK_PRICE_OUTPUT_PER_1K"
    )
    sagemaker_endpoint: str | None = Field(default=None, alias="SAGEMAKER_ENDPOINT")

    allowed_origins: Annotated[frozenset[str], NoDecode] = Field(
        default=DEFAULT_ORIGINS, alias="ALLOWED_ORIGINS"
    )

    cookie_name: str = "nexaro_session"
    cookie_secure: bool = Field(default=False, alias="COOKIE_SECURE")
    session_max_age_seconds: int = Field(default=7 * 24 * 60 * 60, gt=0)

    login_max_attempts: int = Field(default=5, gt=0)
    login_window_seconds: int = Field(default=900, gt=0)
    login_max_tracked_keys: int = Field(default=10_000, gt=0)

    # Por defecto igual que login_max_attempts. Tras la NAT de Docker Desktop todos los clientes
    # llegan con la misma IP (la pasarela): ahí compose lo sube para que nadie bloquee a todos.
    login_ip_max_attempts: int | None = Field(default=None, gt=0, alias="LOGIN_IP_MAX_ATTEMPTS")

    api_key_requests_per_minute: int = Field(default=60, gt=0)

    # Abuso de recursos del modelo (CPU): ritmo por usuario y generaciones simultáneas.
    chat_requests_per_minute: int = Field(default=30, gt=0, alias="CHAT_REQUESTS_PER_MINUTE")
    chat_max_concurrent: int = Field(default=2, gt=0, alias="CHAT_MAX_CONCURRENT")
    chat_max_concurrent_per_user: int = Field(default=2, gt=0, alias="CHAT_MAX_CONCURRENT_PER_USER")
    health_cache_seconds: float = Field(default=0.0, ge=0, alias="HEALTH_CACHE_SECONDS")
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(
        default="INFO", alias="LOG_LEVEL"
    )
    log_format: Literal["json", "text"] = Field(default="json", alias="LOG_FORMAT")
    max_body_bytes: int = Field(default=2 * 1024 * 1024, gt=0, alias="MAX_BODY_BYTES")
    # None = solo en desarrollo. Swagger/OpenAPI describen toda la superficie de la API.
    api_docs: bool | None = Field(default=None, alias="API_DOCS")

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return frozenset(item.strip() for item in value.split(",") if item.strip())
        return value

    @field_validator("ai_provider_order", mode="before")
    @classmethod
    def _split_providers(cls, value: object) -> object:
        if isinstance(value, str):
            return tuple(item.strip() for item in value.split(",") if item.strip())
        return value

    @model_validator(mode="after")
    def _gateway_is_consistent(self) -> "Settings":
        order = self.ai_provider_order
        if not order:
            raise ValueError("AI_PROVIDER_ORDER no puede estar vacío")
        unknown = set(order) - KNOWN_PROVIDERS
        if unknown:
            raise ValueError(f"Proveedores desconocidos en AI_PROVIDER_ORDER: {sorted(unknown)}")
        cloud = set(order) & CLOUD_PROVIDERS
        if not cloud:
            return self
        if not self.ai_allow_cloud:
            raise ValueError(
                "Hay proveedores en la nube en AI_PROVIDER_ORDER: exige AI_ALLOW_CLOUD=true"
            )
        if self.ai_cloud_monthly_budget_usd is None or not self.aws_region:
            raise ValueError("La nube exige AI_CLOUD_MONTHLY_BUDGET_USD y AWS_REGION")
        if "bedrock" in cloud and not (
            self.bedrock_model_id
            and self.bedrock_price_input_per_1k is not None
            and self.bedrock_price_output_per_1k is not None
        ):
            raise ValueError("Bedrock exige BEDROCK_MODEL_ID y los precios por 1.000 tokens")
        if "sagemaker" in cloud and not self.sagemaker_endpoint:
            raise ValueError("SageMaker exige SAGEMAKER_ENDPOINT")
        return self

    @model_validator(mode="after")
    def _production_must_be_secure(self) -> "Settings":
        if self.environment == "production":
            if not self.cookie_secure:
                raise ValueError("En producción COOKIE_SECURE debe ser true")
            if any(origin.startswith("http://") for origin in self.allowed_origins):
                raise ValueError("En producción ALLOWED_ORIGINS debe usar solo https://")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
