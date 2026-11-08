from typing import Protocol

from ai_gateway.schemas import CompletionRequest, CompletionResult


class ChatProvider(Protocol):
    """Interfaz común de proveedores (Ollama, Bedrock, SageMaker, futuros)."""

    @property
    def name(self) -> str: ...

    async def complete(self, request: CompletionRequest) -> CompletionResult: ...

    async def health(self) -> bool: ...
