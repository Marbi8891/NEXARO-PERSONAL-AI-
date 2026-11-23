# AI Gateway

`packages/ai_gateway` is the only path from NEXARO to a language model. Products never call a provider
directly. Design record: [ADR-0004](../decisions/0004-ai-gateway.md),
[ADR-0016](../decisions/0016-gateway-circuit-breaker-and-model-status.md),
[ADR-0023](../decisions/0023-model-selection.md).

← [Architecture overview](overview.md)

## Responsibilities

| Concern | Implementation |
|---|---|
| Provider abstraction | `providers/base.py`: `ChatProvider` / `StreamingChatProvider` protocols |
| Routing and fallback | `Gateway` tries routes in `AI_PROVIDER_ORDER`; falls back only on *unavailability* |
| Policy limits | `GatewayPolicy`: max input chars, max output tokens, timeout, retries, cloud switch, budget |
| Circuit breaker | `breaker.py`: per provider; opens after `AI_BREAKER_THRESHOLD` consecutive failures, retries after the cooldown |
| Streaming | `streaming.py`: chunks plus inference metrics (time to first token, tokens) |
| Usage ledger | `usage.py`: tokens and cost per request, user and API key; feeds dashboards and the monthly budget |
| Model status | `Gateway.describe()` → `GET /api/admin/models` |

## Providers

| Provider | Status | Notes |
|---|---|---|
| **Ollama** | Implemented, verified against a real Ollama | Default; local; lists installed models for the model selector |
| **AWS Bedrock** | Experimental | Tested with test doubles only; requires `boto3` (`INSTALL_AWS=1`) |
| **AWS SageMaker** | Experimental | Same as Bedrock |
| OpenAI, Gemini, others | Not implemented | Planned only on explicit request, because they add cost and send data off-host |

## Model selection

- **Auto** (default): `OLLAMA_MODEL` with the configured fallback order.
- **Pinned**: a conversation can pin any model installed in the primary provider (`GET /api/models`).
  A pinned model has **no fallback** and is never silently replaced; if it is missing the request fails
  with a clear error.
- Not yet available: per-user and per-agent default models (roadmap: Model Manager).

## Privacy guarantees

1. Cloud providers are disabled unless `AI_ALLOW_CLOUD=true`.
2. Enabling a cloud provider also requires a monthly budget (`AI_CLOUD_MONTHLY_BUDGET_USD`), a region
   and the provider's identifiers. If any is missing, **the application refuses to start**.
3. A timeout is never retried (it would double cost and load); only unavailability is.
4. Every request goes through the same limits regardless of provider.

## Adding a provider

1. Implement the `ChatProvider` (and optionally `StreamingChatProvider`) protocol under
   `packages/ai_gateway/providers/<name>/`.
2. Map provider failures to `ai_gateway.errors` (`ProviderUnavailableError`, `ProviderTimeoutError`,
   `ProviderError`) so fallback and the circuit breaker behave correctly.
3. Register it in `apps/api/nexaro_api/gateway.py` and in the settings validation if it is a cloud provider.
4. Test it with a test double; record the decision in an ADR.

The planned **Intelligent Model Router** (task-aware routing) will build on this layer; see
[ROADMAP.md](../../ROADMAP.md).
