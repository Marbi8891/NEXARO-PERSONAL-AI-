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
    user_id: str | None = None  # solo para el registro de uso; los proveedores lo ignoran


class CompletionResult(BaseModel):
    content: str
    model: str
    provider: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    latency_ms: float = 0.0
