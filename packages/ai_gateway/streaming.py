"""Streaming uniforme: si el proveedor no lo soporta, se entrega como un único fragmento."""

from collections.abc import AsyncIterator

from ai_gateway.providers.base import ChatProvider
from ai_gateway.schemas import CompletionRequest, InferenceMetrics, StreamChunk


async def stream_completion(
    provider: ChatProvider, request: CompletionRequest
) -> AsyncIterator[StreamChunk]:
    native = getattr(provider, "stream", None)
    if native is not None:
        async for chunk in native(request):
            yield chunk
        return
    result = await provider.complete(request)
    metrics = result.metrics or InferenceMetrics(
        total_ms=result.latency_ms, prompt_tokens=result.input_tokens, tokens=result.output_tokens
    )
    yield StreamChunk(content=result.content)
    yield StreamChunk(done=True, metrics=metrics)
