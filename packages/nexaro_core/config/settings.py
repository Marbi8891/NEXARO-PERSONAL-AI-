"""Configuración centralizada y validada. Única fuente de lectura de variables de entorno."""

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

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

    allowed_origins: Annotated[frozenset[str], NoDecode] = Field(
        default=DEFAULT_ORIGINS, alias="ALLOWED_ORIGINS"
    )

    cookie_name: str = "nexaro_session"
    cookie_secure: bool = Field(default=False, alias="COOKIE_SECURE")
    session_max_age_seconds: int = Field(default=7 * 24 * 60 * 60, gt=0)

    login_max_attempts: int = Field(default=5, gt=0)
    login_window_seconds: int = Field(default=900, gt=0)
    login_max_tracked_keys: int = Field(default=10_000, gt=0)

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return frozenset(item.strip() for item in value.split(",") if item.strip())
        return value

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
