import asyncio
import io
import json

import boto3
import pytest
from botocore.stub import Stubber

from ai_gateway.errors import ProviderError, ProviderTimeoutError, ProviderUnavailableError
from ai_gateway.providers.bedrock import BedrockProvider
from ai_gateway.providers.sagemaker import SageMakerProvider
from ai_gateway.schemas import ChatMessage, CompletionRequest

MODEL = "anthropic.test-model"
MESSAGES = [
    ChatMessage(role="system", content="sé breve"),
    ChatMessage(role="user", content="hola"),
]
REQUEST = CompletionRequest(model=MODEL, messages=MESSAGES, max_output_tokens=64)


def fake_client(service: str) -> boto3.session.Session:
    return boto3.client(
        service,
        region_name="eu-west-1",
        aws_access_key_id="test",
        aws_secret_access_key="test",
    )


def converse_ok(text: str = "respuesta") -> dict:
    return {
        "output": {"message": {"role": "assistant", "content": [{"text": text}]}},
        "stopReason": "end_turn",
        "usage": {"inputTokens": 11, "outputTokens": 7, "totalTokens": 18},
        "metrics": {"latencyMs": 5},
    }


def test_bedrock_maps_messages_and_usage() -> None:
    client = fake_client("bedrock-runtime")
    with Stubber(client) as stub:
        stub.add_response(
            "converse",
            converse_ok(),
            {
                "modelId": MODEL,
                "messages": [{"role": "user", "content": [{"text": "hola"}]}],
                "system": [{"text": "sé breve"}],
                "inferenceConfig": {"maxTokens": 64},
            },
        )  # los parámetros esperados verifican el mapeo exacto
        result = asyncio.run(BedrockProvider("eu-west-1", client=client).complete(REQUEST))
    assert (result.content, result.provider, result.input_tokens, result.output_tokens) == (
        "respuesta",
        "bedrock",
        11,
        7,
    )


@pytest.mark.parametrize(
    ("code", "error"),
    [
        ("ThrottlingException", ProviderUnavailableError),
        ("ServiceUnavailableException", ProviderUnavailableError),
        ("ModelTimeoutException", ProviderTimeoutError),
        ("AccessDeniedException", ProviderError),
        ("ValidationException", ProviderError),
    ],
)
def test_bedrock_errors_are_translated_without_leaking_details(code: str, error: type) -> None:
    client = fake_client("bedrock-runtime")
    with Stubber(client) as stub:
        stub.add_client_error(
            "converse", service_error_code=code, service_message="arn:aws:SECRETO"
        )
        with pytest.raises(error) as caught:
            asyncio.run(BedrockProvider("eu-west-1", client=client).complete(REQUEST))
    assert "SECRETO" not in str(caught.value)
    assert type(caught.value) is error


def test_bedrock_malformed_response_is_a_provider_error() -> None:
    client = fake_client("bedrock-runtime")
    with Stubber(client) as stub:
        stub.add_response(
            "converse",
            {
                "output": {
                    "message": {
                        "role": "assistant",
                        "content": [{"image": {"format": "png", "source": {"bytes": b"x"}}}],
                    }
                },
                "stopReason": "end_turn",
                "usage": {"inputTokens": 1, "outputTokens": 1, "totalTokens": 2},
                "metrics": {"latencyMs": 1},
            },
        )
        with pytest.raises(ProviderError):
            asyncio.run(BedrockProvider("eu-west-1", client=client).complete(REQUEST))


def sagemaker_body(payload: dict) -> dict:
    return {"Body": _Body(json.dumps(payload).encode()), "ContentType": "application/json"}


class _Body(io.BytesIO):
    """Imita StreamingBody (solo `read`)."""


def test_sagemaker_uses_openai_style_payload_and_parses_usage() -> None:
    client = fake_client("sagemaker-runtime")
    reply = {
        "choices": [{"message": {"role": "assistant", "content": "desde endpoint"}}],
        "usage": {"prompt_tokens": 9, "completion_tokens": 4},
    }
    expected_body = json.dumps(
        {"messages": [m.model_dump() for m in MESSAGES], "max_tokens": 64}
    ).encode()
    with Stubber(client) as stub:
        stub.add_response(
            "invoke_endpoint",
            sagemaker_body(reply),
            {
                "EndpointName": "mi-endpoint",
                "ContentType": "application/json",
                "Accept": "application/json",
                "Body": expected_body,
            },
        )
        provider = SageMakerProvider("eu-west-1", client=client)
        result = asyncio.run(provider.complete(REQUEST.model_copy(update={"model": "mi-endpoint"})))
    assert (result.content, result.provider, result.input_tokens, result.output_tokens) == (
        "desde endpoint",
        "sagemaker",
        9,
        4,
    )


def test_sagemaker_unexpected_format_and_service_errors() -> None:
    client = fake_client("sagemaker-runtime")
    with Stubber(client) as stub:
        stub.add_response("invoke_endpoint", sagemaker_body({"otro": "formato"}))
        stub.add_client_error("invoke_endpoint", service_error_code="ServiceUnavailable")
        provider = SageMakerProvider("eu-west-1", client=client)
        with pytest.raises(ProviderError):
            asyncio.run(provider.complete(REQUEST))
        with pytest.raises(ProviderUnavailableError):
            asyncio.run(provider.complete(REQUEST))


def test_cloud_providers_report_configuration_only() -> None:
    assert asyncio.run(BedrockProvider("eu-west-1", client=object()).health()) is True
    assert asyncio.run(SageMakerProvider("eu-west-1", client=object()).health()) is True
