from collections.abc import AsyncIterator
from typing import Protocol

from ai_gateway.schemas import CompletionRequest, CompletionResult, StreamChunk


class ChatProvider(Protocol):
    """Interfaz común de proveedores (Ollama, Bedrock, SageMaker, futuros)."""

    @property
    def name(self) -> str: ...

    async def complete(self, request: CompletionRequest) -> CompletionResult: ...

    async def health(self) -> bool: ...


class StreamingChatProvider(ChatProvider, Protocol):
    """Proveedor con streaming real. Los demás se sirven como un único fragmento."""

    def stream(self, request: CompletionRequest) -> AsyncIterator[StreamChunk]: ...
