"""Contratos del AI Gateway. Ningún módulo de negocio depende de un proveedor concreto."""

from typing import Literal

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class CompletionRequest(BaseModel):
    model: str = Field(min_length=1)
    messages: list[ChatMessage] = Field(min_length=1)
    max_output_tokens: int | None = Field(default=None, gt=0)
    timeout_seconds: float | None = Field(default=None, gt=0)
    # Solo para el registro de uso; los proveedores los ignoran.
    user_id: str | None = None
    organization_id: str | None = None
    api_key_id: str | None = None


class InferenceMetrics(BaseModel):
    """Tiempos de una inferencia en milisegundos. Lo que el proveedor no informa queda en None."""

    ttft_ms: float | None = None  # hasta el primer contenido (medido por NEXARO)
    load_ms: float | None = None  # carga del modelo en memoria (informa Ollama)
    prompt_eval_ms: float | None = None
    generation_ms: float | None = None
    total_ms: float | None = None
    prompt_tokens: int | None = None
    tokens: int | None = None
    done_reason: str | None = None  # «stop», «length» (cortada por num_predict)...

    @property
    def tokens_per_second(self) -> float | None:
        if self.tokens and self.generation_ms:
            return round(self.tokens / (self.generation_ms / 1000), 2)
        return None


class StreamChunk(BaseModel):
    """Fragmento de una respuesta en streaming. El último trae `done=True` y las métricas."""

    content: str = ""
    done: bool = False
    metrics: InferenceMetrics | None = None


class CompletionResult(BaseModel):
    content: str
    model: str
    provider: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    latency_ms: float = 0.0
    metrics: InferenceMetrics | None = None
