# app/routers/copilot_router.py
import logging
from typing import List, Optional
from datetime import datetime, timezone
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.core.database import get_db
from app.core.security import get_current_user, TokenData
from app.models.copilot_session import CopilotSesion, CopilotMensaje
from app.schemas.copilot import (
    CopilotChatIn,
    CopilotChatOut,
    CopilotSessionCreate,
    CopilotSessionOut,
    CopilotMessageOut,
    CopilotMessageItem
)
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

def _validar_rol_copilot(token_data: TokenData, actor) -> None:
    if actor.es_admin() or token_data.role == "admin" or not actor.suscriptor_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="El Copiloto Inteligente MCP está disponible exclusivamente para empresas suscriptoras."
        )

def _verificar_acceso_sesion(sesion: CopilotSesion, actor) -> None:
    if not actor.suscriptor_id or sesion.suscriptor_id != actor.suscriptor_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acceso denegado: esta sesión de chat pertenece a otra empresa."
        )


# ────────────────── GESTIÓN DE SESIONES DE CHAT ──────────────────

@router.get("/sessions", response_model=List[CopilotSessionOut], summary="Listar sesiones de Copilot del usuario")
async def list_copilot_sessions(
    db: Session = Depends(get_db),
    token_data: TokenData = Depends(get_current_user)
):
    actor = resolver_actor_context(db, token_data)
    _validar_rol_copilot(token_data, actor)

    sesiones = (
        db.query(CopilotSesion)
        .filter(CopilotSesion.suscriptor_id == actor.suscriptor_id)
        .order_by(CopilotSesion.actualizado_en.desc())
        .all()
    )

    resultados = []
    for s in sesiones:
        msg_count = db.query(func.count(CopilotMensaje.id)).filter(CopilotMensaje.sesion_id == s.id).scalar() or 0
        resultados.append(CopilotSessionOut(
            id=s.id,
            title=s.titulo,
            campana_id=s.campana_id,
            created_at=s.creado_en.isoformat() if s.creado_en else "",
            updated_at=s.actualizado_en.isoformat() if s.actualizado_en else "",
            message_count=msg_count
        ))

    return resultados


@router.post("/sessions", response_model=CopilotSessionOut, status_code=status.HTTP_201_CREATED, summary="Crear nueva sesión de Copilot")
async def create_copilot_session(
    payload: CopilotSessionCreate,
    db: Session = Depends(get_db),
    token_data: TokenData = Depends(get_current_user)
):
    actor = resolver_actor_context(db, token_data)
    _validar_rol_copilot(token_data, actor)
    now = datetime.now(timezone.utc)

    nueva_sesion = CopilotSesion(
        suscriptor_id=actor.suscriptor_id,
        user_id=actor.user_id,
        rol=actor.role,
        titulo=payload.title or "Nueva conversación",
        campana_id=payload.campana_id,
        creado_en=now,
        actualizado_en=now
    )
    db.add(nueva_sesion)
    db.commit()
    db.refresh(nueva_sesion)

    return CopilotSessionOut(
        id=nueva_sesion.id,
        title=nueva_sesion.titulo,
        campana_id=nueva_sesion.campana_id,
        created_at=nueva_sesion.creado_en.isoformat(),
        updated_at=nueva_sesion.actualizado_en.isoformat(),
        message_count=0
    )


@router.get("/sessions/{session_id}/messages", response_model=List[CopilotMessageOut], summary="Obtener historial de mensajes de una sesión")
async def get_session_messages(
    session_id: UUID,
    db: Session = Depends(get_db),
    token_data: TokenData = Depends(get_current_user)
):
    actor = resolver_actor_context(db, token_data)
    _validar_rol_copilot(token_data, actor)
    sesion = db.query(CopilotSesion).filter(CopilotSesion.id == session_id).first()
    if not sesion:
        raise HTTPException(status_code=404, detail="Sesión no encontrada")

    _verificar_acceso_sesion(sesion, actor)

    mensajes = (
        db.query(CopilotMensaje)
        .filter(CopilotMensaje.sesion_id == session_id)
        .order_by(CopilotMensaje.creado_en.asc())
        .all()
    )

    return [
        CopilotMessageOut(
            id=m.id,
            sender=m.sender,
            text=m.text,
            tools_used=m.tools_used or [],
            fuentes_citadas=m.fuentes_citadas or [],
            created_at=m.creado_en.isoformat() if m.creado_en else ""
        )
        for m in mensajes
    ]


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Eliminar una sesión de Copilot")
async def delete_copilot_session(
    session_id: UUID,
    db: Session = Depends(get_db),
    token_data: TokenData = Depends(get_current_user)
):
    actor = resolver_actor_context(db, token_data)
    _validar_rol_copilot(token_data, actor)
    sesion = db.query(CopilotSesion).filter(CopilotSesion.id == session_id).first()
    if not sesion:
        raise HTTPException(status_code=404, detail="Sesión no encontrada")

    _verificar_acceso_sesion(sesion, actor)

    db.delete(sesion)
    db.commit()
    return None


# ────────────────── CHAT Y ORQUESTACIÓN CON PERSISTENCIA ──────────────────

@router.post("/chat", response_model=CopilotChatOut, summary="Conversar con el Copiloto Inteligente de la Empresa")
@agente_copilot_alias_router.post("", response_model=CopilotChatOut, summary="Alias conversar con el Copiloto")
async def chat_copilot_endpoint(
    payload: CopilotChatIn,
    db: Session = Depends(get_db),
    token_data: TokenData = Depends(get_current_user)
):
    """
    Endpoint principal para el Chatbot / Copiloto inteligente en la Web App del SaaS.
    - Soporta sesiones server-side persistentes vía session_id.
    - Si no se envía session_id, crea una sesión automáticamente.
    - Ejecuta herramientas MCP del dominio de forma segura sin acceso SQL directo.
    - Garantiza aislamiento multi-tenant estricto.
    """
    actor = resolver_actor_context(db, token_data)
    _validar_rol_copilot(token_data, actor)
    now = datetime.now(timezone.utc)

    # 1. Resolver o crear la sesión
    sesion: Optional[CopilotSesion] = None
    if payload.session_id:
        sesion = db.query(CopilotSesion).filter(CopilotSesion.id == payload.session_id).first()
        if not sesion:
            raise HTTPException(status_code=404, detail="Sesión no encontrada")
        _verificar_acceso_sesion(sesion, actor)
    else:
        # Autocrear sesión para garantizar persistencia y trazabilidad en el frontend
        titulo_inicial = (payload.message[:35] + "...") if len(payload.message) > 35 else payload.message
        sesion = CopilotSesion(
            suscriptor_id=actor.suscriptor_id,
            user_id=actor.user_id,
            rol=actor.role,
            titulo=titulo_inicial or "Nueva conversación",
            campana_id=payload.campana_id,
            creado_en=now,
            actualizado_en=now
        )
        db.add(sesion)
        db.commit()
        db.refresh(sesion)

    # 2. Persistir mensaje del usuario
    msg_usuario = CopilotMensaje(
        sesion_id=sesion.id,
        sender="user",
        text=payload.message,
        tools_used=[],
        fuentes_citadas=[],
        creado_en=now
    )
    db.add(msg_usuario)
    db.commit()

    # 3. Construir historial de contexto (desde DB o payload)
    historial_list = []
    if payload.history and len(payload.history) > 0:
        historial_list = [{"sender": m.sender, "text": m.text} for m in payload.history]
    else:
        # Cargar últimos 6 mensajes de la sesión
        mensajes_previos = (
            db.query(CopilotMensaje)
            .filter(CopilotMensaje.sesion_id == sesion.id, CopilotMensaje.id != msg_usuario.id)
            .order_by(CopilotMensaje.creado_en.asc())
            .all()
        )
        historial_list = [{"sender": m.sender, "text": m.text} for m in mensajes_previos[-6:]]

    # 4. Procesar consulta a través del orquestador MCP
    campana_ctx = payload.campana_id or sesion.campana_id
    resultado = await procesar_mensaje_copilot(
        db=db,
        actor=actor,
        mensaje=payload.message,
        historial=historial_list,
        campana_id=campana_ctx
    )

    # 5. Persistir mensaje del asistente
    answer_text = resultado.get("answer", "")
    tools_used_raw = resultado.get("tools_used") or []
    fuentes_raw = resultado.get("fuentes_citadas") or []

    msg_asistente = CopilotMensaje(
        sesion_id=sesion.id,
        sender="assistant",
        text=answer_text,
        tools_used=tools_used_raw,
        fuentes_citadas=fuentes_raw,
        creado_en=datetime.now(timezone.utc)
    )
    db.add(msg_asistente)

    # 6. Actualizar sesión (timestamp y título si era default)
    sesion.actualizado_en = datetime.now(timezone.utc)
    if sesion.titulo in ("Nueva conversación", "Nueva conversacion", ""):
        sesion.titulo = (payload.message[:35] + "...") if len(payload.message) > 35 else payload.message
    db.commit()

    return CopilotChatOut(
        answer=answer_text,
        session_id=sesion.id,
        tools_used=tools_used_raw,
        fuentes_citadas=fuentes_raw,
        suggested_actions=resultado.get("suggested_actions") or []
    )
