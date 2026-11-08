from typing import Any

from fastapi import APIRouter, HTTPException, Request

from ai_gateway.errors import ProviderError
from nexaro_api.deps import Ctx, CurrentUser, validate_origin
from nexaro_api.schemas import ChatRequest
from products.personal_ai.service import ConversationNotFoundError

router = APIRouter(prefix="/api", tags=["personal-ai"])

NOT_FOUND = HTTPException(status_code=404, detail="Conversación no encontrada")


@router.post("/chat")
async def chat(request: Request, body: ChatRequest, user: CurrentUser, ctx: Ctx) -> dict[str, Any]:
    validate_origin(request, ctx)

    try:
        outcome = await ctx.personal_ai.chat(user["id"], body.message, body.conversation_id)
    except ConversationNotFoundError:
        raise NOT_FOUND from None
    except ProviderError as exc:
        # El detalle del proveedor (URLs internas, etc.) no se devuelve al cliente.
        raise HTTPException(status_code=502, detail="Error al consultar el servicio de IA") from exc

    return {"conversation_id": outcome.conversation_id, "answer": outcome.answer}


@router.get("/conversations")
def list_conversations(user: CurrentUser, ctx: Ctx) -> dict[str, Any]:
    return {"conversations": ctx.personal_ai.list_conversations(user["id"])}


@router.get("/conversations/{conversation_id}")
def get_conversation(conversation_id: str, user: CurrentUser, ctx: Ctx) -> dict[str, Any]:
    try:
        return ctx.personal_ai.get_conversation(user["id"], conversation_id)
    except ConversationNotFoundError:
        raise NOT_FOUND from None
