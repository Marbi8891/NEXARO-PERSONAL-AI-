import asyncio
import time
from typing import Any

import boto3
from botocore.config import Config

from ai_gateway.errors import ProviderError
from ai_gateway.providers.aws_errors import translate
from ai_gateway.schemas import CompletionRequest, CompletionResult


class BedrockProvider:
    """Amazon Bedrock vía la API Converse. Las credenciales salen de la cadena estándar de AWS
    (rol/entorno); nunca se leen ni se guardan aquí."""

    name = "bedrock"

    def __init__(
        self,
        region: str,
        *,
        timeout_seconds: float = 60.0,
        client: Any | None = None,
    ) -> None:
        # botocore no admite timeout por llamada: el de la política se fija al crear el cliente.
        self._client = client or boto3.client(
            "bedrock-runtime",
            region_name=region,
            config=Config(
                read_timeout=timeout_seconds,
                connect_timeout=5,
                retries={"max_attempts": 1},  # los reintentos los decide el gateway
            ),
        )

    async def complete(self, request: CompletionRequest) -> CompletionResult:
        system = [{"text": m.content} for m in request.messages if m.role == "system"]
        conversation = [
            {"role": m.role, "content": [{"text": m.content}]}
            for m in request.messages
            if m.role != "system"
        ]
        arguments: dict[str, Any] = {"modelId": request.model, "messages": conversation}
        if system:
            arguments["system"] = system
        if request.max_output_tokens is not None:
            arguments["inferenceConfig"] = {"maxTokens": request.max_output_tokens}

        started = time.perf_counter()
        try:
            response = await asyncio.to_thread(self._client.converse, **arguments)
            content = response["output"]["message"]["content"][0]["text"]
            usage = response.get("usage", {})
        except Exception as exc:
            raise translate(exc, "Bedrock") from exc

        if not isinstance(content, str):
            raise ProviderError("Respuesta no válida de Bedrock")
        return CompletionResult(
            content=content,
            model=request.model,
            provider=self.name,
            input_tokens=usage.get("inputTokens"),
            output_tokens=usage.get("outputTokens"),
            latency_ms=(time.perf_counter() - started) * 1000,
        )

    async def health(self) -> bool:
        """Solo comprueba que hay cliente configurado; no hace una llamada (costaría dinero)."""
        return self._client is not None
