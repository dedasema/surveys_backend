# app/routers/ingesta_router.py
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, status, HTTPException
from app.core.security import get_admin_user, get_current_user
from app.schemas.auth import TokenData
from app.services.queue_service import enqueue_channel_message, get_queue_metrics

router = APIRouter(tags=["Canales - Ingesta Asíncrona (RF19)"])

class IngestaPayload(BaseModel):
    canal: str = Field(..., description="Canal de entrada: 'gmail', 'ocr', 'voz', 'web', 'whatsapp'")
    contenido: Any = Field(..., description="Contenido en bruto (texto, json o referencia a archivo)")
    tipo: str = Field("texto", description="Tipo de contenido: 'texto', 'audio_url', 'imagen_ocr'")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Metadatos adicionales (remitente, id de entrega, etc.)")

@router.post(
    "/canales/ingesta",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Ingesta asíncrona unificada para Gmail, OCR y Voz"
)
async def ingesta_multicanal_endpoint(
    payload: IngestaPayload
):
    """
    Recibe de inmediato respuestas desde Gmail, OCR físico o audio de voz,
    las normaliza y las encola en Redis para procesamiento asíncrono desacoplado.
    Responde instantáneamente HTTP 202 sin esperar la ejecución de IA.
    """
    canal_limpio = payload.canal.lower().strip()
    if canal_limpio not in ["gmail", "ocr", "voz", "web", "whatsapp", "email"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Canal no soportado: '{payload.canal}'"
        )

    res = enqueue_channel_message(
        canal=canal_limpio,
        contenido=payload.contenido,
        tipo=payload.tipo,
        metadata=payload.metadata
    )

    return res

@router.get(
    "/admin/colas/estado",
    status_code=status.HTTP_200_OK,
    summary="Métricas de la cola de ingesta asíncrona (RF19)"
)
def get_colas_estado_endpoint(
    admin_data: TokenData = Depends(get_admin_user)
):
    """
    Excluisivo para administradores: Retorna el estado en tiempo real de la cola
    (mensajes pendientes, tareas en proceso, fallidos/dead-letter y procesados).
    """
    return get_queue_metrics()
