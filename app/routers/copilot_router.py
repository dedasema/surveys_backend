# app/routers/copilot_router.py
import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user, TokenData
from app.schemas.copilot import CopilotChatIn, CopilotChatOut
from app.services.mcp.context import resolver_actor_context
from app.services.copilot_service import procesar_mensaje_copilot

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/copilot",
    tags=["Copiloto Inteligente (SaaS AI)"]
)

agente_copilot_alias_router = APIRouter(
    prefix="/agente/copilot",
    tags=["Copiloto Inteligente (SaaS AI)"]
)

@router.post("/chat", response_model=CopilotChatOut, summary="Conversar con el Copiloto Inteligente de la Empresa")
@agente_copilot_alias_router.post("", response_model=CopilotChatOut, summary="Alias conversar con el Copiloto")
async def chat_copilot_endpoint(
    payload: CopilotChatIn,
    db: Session = Depends(get_db),
    token_data: TokenData = Depends(get_current_user)
):
    """
    Endpoint principal para el Chatbot / Copiloto inteligente en la Web App del SaaS.
    - Autenticado vía JWT Bearer.
    - Ejecuta herramientas MCP del dominio de forma segura sin acceso SQL directo.
    - Garantiza aislamiento multi-tenant estricto.
    """
    actor = resolver_actor_context(db, token_data)

    historial_list = [
        {"sender": m.sender, "text": m.text}
        for m in (payload.history or [])
    ]

    resultado = await procesar_mensaje_copilot(
        db=db,
        actor=actor,
        mensaje=payload.message,
        historial=historial_list,
        campana_id=payload.campana_id
    )

    return CopilotChatOut(**resultado)
