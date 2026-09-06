# app/routers/audio_respuestas_router.py
import os
import uuid
import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.survey import EntregaEncuesta, PreguntaEncuesta
from app.models.audio_respuesta import AudioRespuesta
from app.services.multimodal_service import transcribir_audio, validar_archivo_multimodal

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/encuestas", tags=["Audio Respuestas (RF18)"])

UPLOAD_AUDIO_DIR = "uploads/audio"
os.makedirs(UPLOAD_AUDIO_DIR, exist_ok=True)

@router.post(
    "/{entrega_id}/audio-respuesta",
    status_code=status.HTTP_201_CREATED,
    summary="Subir y transcribir audio de respuesta de encuesta (RF18)"
)
async def subir_audio_respuesta(
    entrega_id: uuid.UUID,
    archivo: UploadFile = File(...),
    pregunta_id: Optional[uuid.UUID] = Form(None),
    db: Session = Depends(get_db)
):
    # 1. Validar existencia de la entrega
    entrega = db.query(EntregaEncuesta).filter(EntregaEncuesta.id == entrega_id).first()
    if not entrega:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Entrega de encuesta {entrega_id} no encontrada"
        )

    # 2. Si se proporciona pregunta_id, validar que exista
    if pregunta_id:
        pregunta = db.query(PreguntaEncuesta).filter(PreguntaEncuesta.id == pregunta_id).first()
        if not pregunta:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Pregunta {pregunta_id} no encontrada"
            )

    # 3. Leer y validar archivo
    try:
        contenido = await archivo.read()
        mime_type = archivo.content_type or "audio/mpeg"
        validar_archivo_multimodal(contenido, mime_type)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

    # 4. Guardar archivo en disco
    file_ext = archivo.filename.split(".")[-1] if archivo.filename and "." in archivo.filename else "mp3"
    nombre_archivo = f"{uuid.uuid4()}.{file_ext}"
    ruta_guardado = os.path.join(UPLOAD_AUDIO_DIR, nombre_archivo)
    
    with open(ruta_guardado, "wb") as f:
        f.write(contenido)

    archivo_url = f"/{UPLOAD_AUDIO_DIR}/{nombre_archivo}"

    # 5. Crear registro AudioRespuesta en estado pendiente
    audio_record = AudioRespuesta(
        entrega_id=entrega_id,
        pregunta_id=pregunta_id,
        archivo_url=archivo_url,
        formato=file_ext.lower(),
        estado_transcripcion="pendiente"
    )
    db.add(audio_record)
    db.commit()
    db.refresh(audio_record)

    # 6. Transcribir el audio usando Gemini Multimodal
    try:
        transcripcion = await transcribir_audio(contenido, mime_type)
        audio_record.transcripcion_texto = transcripcion
        audio_record.estado_transcripcion = "completado"
    except Exception as e:
        logger.error("Error transcribiendo audio %s: %s", audio_record.id, e)
        audio_record.estado_transcripcion = "error"
        audio_record.error_detalle = str(e)
    
    db.commit()
    db.refresh(audio_record)

    return {
        "id": str(audio_record.id),
        "entrega_id": str(audio_record.entrega_id),
        "pregunta_id": str(audio_record.pregunta_id) if audio_record.pregunta_id else None,
        "archivo_url": audio_record.archivo_url,
        "formato": audio_record.formato,
        "estado_transcripcion": audio_record.estado_transcripcion,
        "transcripcion_texto": audio_record.transcripcion_texto,
        "error_detalle": audio_record.error_detalle,
        "creado_en": audio_record.creado_en.isoformat() if audio_record.creado_en else None
    }

@router.get(
    "/audio-respuesta/{audio_id}/estado",
    summary="Consultar estado y transcripción de un audio grabado (RF18)"
)
async def obtener_estado_audio(
    audio_id: uuid.UUID,
    db: Session = Depends(get_db)
):
    audio_record = db.query(AudioRespuesta).filter(AudioRespuesta.id == audio_id).first()
    if not audio_record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Registro de audio {audio_id} no encontrado"
        )

    return {
        "id": str(audio_record.id),
        "entrega_id": str(audio_record.entrega_id),
        "pregunta_id": str(audio_record.pregunta_id) if audio_record.pregunta_id else None,
        "archivo_url": audio_record.archivo_url,
        "formato": audio_record.formato,
        "estado_transcripcion": audio_record.estado_transcripcion,
        "transcripcion_texto": audio_record.transcripcion_texto,
        "error_detalle": audio_record.error_detalle,
        "creado_en": audio_record.creado_en.isoformat() if audio_record.creado_en else None
    }
