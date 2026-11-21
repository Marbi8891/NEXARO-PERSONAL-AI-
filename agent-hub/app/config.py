from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    ollama_base_url: str = "http://localhost:11434"
    ollama_default_model: str = "qwen2.5:3b"
    agent_catalogue_path: str = "../docs/agents/catalogue.json"
    cors_origins: str = "http://localhost:8080,http://localhost:5173"
    request_timeout_seconds: float = 120.0
    max_message_chars: int = 12000
    max_context_chars: int = 20000

    @property
    def origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def catalogue_path(self) -> Path:
        path = Path(self.agent_catalogue_path)
        if not path.is_absolute():
            path = Path(__file__).resolve().parents[2] / path
        return path.resolve()

settings = Settings()
