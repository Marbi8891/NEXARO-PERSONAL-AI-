import asyncio
import json
import time
from typing import Any

import boto3
from botocore.config import Config

from ai_gateway.errors import ProviderError
from ai_gateway.providers.aws_errors import translate
from ai_gateway.schemas import CompletionRequest, CompletionResult


class SageMakerProvider:
    """Endpoint de SageMaker.

    ASSUMPTION / VERIFY: el formato de entrada y salida depende del contenedor del endpoint.
    Aquí se asume una API tipo OpenAI Chat Completions (`messages`, `choices[0].message`), que es
    lo que exponen los contenedores TGI y vLLM más habituales. Hay que comprobarlo contra el
    endpoint real antes de usarlo; con otro contenedor basta con cambiar `_payload` y `_parse`.
    """

    name = "sagemaker"

    def __init__(
        self,
        region: str,
        *,
        timeout_seconds: float = 60.0,
        client: Any | None = None,
    ) -> None:
        self._client = client or boto3.client(
            "sagemaker-runtime",
            region_name=region,
            config=Config(
                read_timeout=timeout_seconds, connect_timeout=5, retries={"max_attempts": 1}
            ),
        )

    @staticmethod
    def _payload(request: CompletionRequest) -> dict[str, Any]:
        payload: dict[str, Any] = {"messages": [m.model_dump() for m in request.messages]}
        if request.max_output_tokens is not None:
            payload["max_tokens"] = request.max_output_tokens
        return payload

    @staticmethod
    def _parse(body: dict[str, Any]) -> tuple[str, int | None, int | None]:
        usage = body.get("usage", {})
        return (
            body["choices"][0]["message"]["content"],
            usage.get("prompt_tokens"),
            usage.get("completion_tokens"),
        )

    async def complete(self, request: CompletionRequest) -> CompletionResult:
        """`request.model` es el nombre del endpoint."""
        started = time.perf_counter()
        try:
            response = await asyncio.to_thread(
                self._client.invoke_endpoint,
                EndpointName=request.model,
                ContentType="application/json",
                Accept="application/json",
                Body=json.dumps(self._payload(request)).encode(),
            )
            content, input_tokens, output_tokens = self._parse(json.loads(response["Body"].read()))
        except Exception as exc:
            raise translate(exc, "SageMaker") from exc

        if not isinstance(content, str):
            raise ProviderError("Respuesta no válida de SageMaker")
        return CompletionResult(
            content=content,
            model=request.model,
            provider=self.name,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=(time.perf_counter() - started) * 1000,
        )

    async def health(self) -> bool:
        """Solo comprueba configuración; consultar el estado exige el cliente `sagemaker`."""
        return self._client is not None
