"""Ensamblado del AI Gateway a partir de la configuración (raíz de composición)."""

from ai_gateway.gateway import Gateway, Route
from ai_gateway.policy import GatewayPolicy
from ai_gateway.providers.base import ChatProvider
from ai_gateway.providers.ollama import OllamaProvider
from ai_gateway.usage import ModelPrice, UsageStore
from nexaro_core.config import CLOUD_PROVIDERS, Settings
from nexaro_core.database import Database


def build_gateway(settings: Settings, database: Database) -> Gateway:
    providers: dict[str, ChatProvider] = {}
    routes: list[Route] = []
    prices: dict[tuple[str, str], ModelPrice] = {}

    for name in settings.ai_provider_order:
        if name == "ollama":
            providers[name] = OllamaProvider(
                settings.ollama_base_url,
                keep_alive=settings.ollama_keep_alive,
                num_ctx=settings.ollama_num_ctx,
                num_thread=settings.ollama_num_thread,
            )
            routes.append(Route(name, settings.ollama_model))
        elif name == "bedrock":
            from ai_gateway.providers.bedrock import BedrockProvider  # boto3 solo si se usa

            assert settings.aws_region and settings.bedrock_model_id  # garantizado por Settings
            providers[name] = BedrockProvider(
                settings.aws_region, timeout_seconds=settings.ai_timeout_seconds
            )
            routes.append(Route(name, settings.bedrock_model_id))
            prices[(name, settings.bedrock_model_id)] = ModelPrice(
                settings.bedrock_price_input_per_1k or 0.0,
                settings.bedrock_price_output_per_1k or 0.0,
            )
        elif name == "sagemaker":
            from ai_gateway.providers.sagemaker import SageMakerProvider

            assert settings.aws_region and settings.sagemaker_endpoint
            providers[name] = SageMakerProvider(
                settings.aws_region, timeout_seconds=settings.ai_timeout_seconds
            )
            routes.append(Route(name, settings.sagemaker_endpoint))  # coste por token: desconocido

    return Gateway(
        providers,
        routes,
        GatewayPolicy(
            max_input_chars=settings.ai_max_input_chars,
            max_output_tokens=settings.ai_max_output_tokens,
            timeout_seconds=settings.ai_timeout_seconds,
            max_retries=settings.ai_max_retries,
            allow_cloud=settings.ai_allow_cloud,
            cloud_monthly_budget_usd=settings.ai_cloud_monthly_budget_usd,
        ),
        cloud=CLOUD_PROVIDERS,
        prices=prices,
        usage=UsageStore(database),
    )
