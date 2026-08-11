from typing import List, Optional
from sqlalchemy.orm import Session, joinedload
from uuid import UUID
from datetime import datetime
from fastapi import HTTPException, status

from app.core.constants import (
    ESTADO_PENDIENTE, ESTADO_ENVIADO, 
    ESTADO_RESPONDIDO, ESTADO_FALLIDO
)
from app.models.survey import (
    CampanaEncuesta, EntregaEncuesta, RespuestaEncuesta, 
    PlantillaEncuesta, PreguntaEncuesta, OpcionEncuesta
)
from app.schemas.campanas_schema import CampanaCreate, CampanaUpdate

# Estados de campaña según la DB
ESTADO_BORRADOR = 1
ESTADO_PROGRAMADA = 2
ESTADO_ENVIADA = 3
ESTADO_CERRADA = 4

def create_campana(db: Session, payload: CampanaCreate, suscriptor_id: UUID) -> CampanaEncuesta:
    campana = CampanaEncuesta(
        **payload.model_dump(),
        suscriptor_id=suscriptor_id,
        estado_id=ESTADO_BORRADOR  
    )
    db.add(campana)
    db.commit()
    db.refresh(campana)
    return campana

def get_campana(db: Session, campana_id: UUID) -> Optional[CampanaEncuesta]:
    return db.query(CampanaEncuesta).filter(CampanaEncuesta.id == campana_id).first()

def list_campanas(db: Session, suscriptor_id: UUID) -> List[CampanaEncuesta]:
    return db.query(CampanaEncuesta).filter(CampanaEncuesta.suscriptor_id == suscriptor_id).all()

def validate_estado_transition(estado_actual: int, nuevo_estado: int):
    """Valida las transiciones permitidas de estados"""
    transiciones_validas = {
        ESTADO_BORRADOR: [ESTADO_PROGRAMADA],
        ESTADO_PROGRAMADA: [ESTADO_ENVIADA, ESTADO_BORRADOR],
        ESTADO_ENVIADA: [ESTADO_CERRADA],
        ESTADO_CERRADA: [] 
    }
    
    if nuevo_estado not in transiciones_validas.get(estado_actual, []):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Transición de estado no válida: {estado_actual} -> {nuevo_estado}"
        )

def update_campana(db: Session, campana_id: UUID, payload: CampanaUpdate) -> Optional[CampanaEncuesta]:
    campana = get_campana(db, campana_id)
    if not campana:
        return None

    update_data = payload.model_dump(exclude_unset=True)
    
    # Validar transición de estado si se está actualizando
    if 'estado_id' in update_data:
        nuevo_estado = update_data['estado_id']
        validate_estado_transition(campana.estado_id, nuevo_estado)
        
        # Validaciones adicionales según el estado
        if nuevo_estado == ESTADO_PROGRAMADA:
            if not campana.plantilla_id and not update_data.get('plantilla_id'):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="No se puede programar una campaña sin plantilla"
                )
            if not campana.programada_en and not update_data.get('programada_en'):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Se requiere fecha de programación"
                )
    
    for field, value in update_data.items():
        setattr(campana, field, value)
    
    db.commit()
    db.refresh(campana)
    return campana

def delete_campana(db: Session, campana_id: UUID) -> bool:
    campana = get_campana(db, campana_id)
    if not campana:
        return False
    db.delete(campana)
    db.commit()
    return True

def update_estado_campana(
    db: Session,
    campana_id: UUID,
    nuevo_estado: int,
    check_transitions: bool = True
) -> Optional[CampanaEncuesta]:
    """
    Actualiza el estado de una campaña validando las transiciones permitidas
    """
    campana = get_campana(db, campana_id)
    if not campana:
        return None

    # Validar transiciones permitidas
    if check_transitions:
        transiciones_validas = {
            ESTADO_BORRADOR: [ESTADO_PROGRAMADA],
            ESTADO_PROGRAMADA: [ESTADO_ENVIADA, ESTADO_BORRADOR],
            ESTADO_ENVIADA: [ESTADO_CERRADA],
            ESTADO_CERRADA: []  # Estado final, no permite transiciones
        }

        if nuevo_estado not in transiciones_validas.get(campana.estado_id, []):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Transición de estado no válida: {campana.estado_id} -> {nuevo_estado}"
            )

    # Validaciones específicas según el estado
    if nuevo_estado == ESTADO_PROGRAMADA:
        if not campana.plantilla_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No se puede programar una campaña sin plantilla"
            )
        if not campana.programada_en:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Se requiere fecha de programación"
            )

    campana.estado_id = nuevo_estado
    db.commit()
    db.refresh(campana)
    return campana

def get_campana_full_detail(db: Session, campana_id: UUID) -> Optional[CampanaEncuesta]:
    """Obtiene una campaña con todos sus detalles y relaciones"""
    campana = (
        db.query(CampanaEncuesta)
        .options(
            # Cargar plantilla con sus preguntas y opciones
            joinedload(CampanaEncuesta.plantilla)
            .joinedload(PlantillaEncuesta.preguntas)
            .joinedload(PreguntaEncuesta.opciones),
            
            # Cargar entregas con sus destinatarios y respuestas
            joinedload(CampanaEncuesta.entregas)
            .joinedload(EntregaEncuesta.destinatario),
            
            joinedload(CampanaEncuesta.entregas)
            .joinedload(EntregaEncuesta.respuestas)
            .joinedload(RespuestaEncuesta.respuestas_preguntas)
        )
        .filter(CampanaEncuesta.id == campana_id)
        .first()
    )

    if campana:
        # Agregar contadores
        campana.total_entregas = len(campana.entregas)
        campana.total_respondidas = sum(1 for e in campana.entregas if e.estado_id == 3)  # ESTADO_RESPONDIDO
        campana.total_pendientes = campana.total_entregas - campana.total_respondidas

    return campana


async def procesar_campanas_programadas(db: Session) -> dict:
    """
    Procesa el envío automático de correos de campañas programadas
    cuya fecha 'programada_en' sea menor o igual a la hora actual (<= now()).
    Es idempotente y retorna un resumen JSON con el resultado.
    """
    from datetime import datetime, timezone
    from app.services.email_service import enviar_email
    from app.services.entregas_service import _generar_url_encuesta
    from app.models.suscriptor import Suscriptor

    now_utc = datetime.now(timezone.utc)

    # 1. Buscar campañas programadas cuya fecha sea <= now()
    campanas_programadas = (
        db.query(CampanaEncuesta)
        .options(
            joinedload(CampanaEncuesta.entregas).joinedload(EntregaEncuesta.destinatario)
        )
        .filter(
            CampanaEncuesta.estado_id == ESTADO_PROGRAMADA,
            CampanaEncuesta.programada_en.isnot(None),
            CampanaEncuesta.programada_en <= now_utc
        )
        .all()
    )

    total_procesadas = len(campanas_programadas)
    enviados = 0
    fallidos = 0
    omitidos = 0
    campanas_actualizadas = 0
    detalles = []

    for campana in campanas_programadas:
        suscriptor = db.get(Suscriptor, campana.suscriptor_id)
        nombre_empresa = suscriptor.nombre if suscriptor else "SurveySaaS"
        
        entregas_pendientes = [
            e for e in campana.entregas 
            if e.estado_id == ESTADO_PENDIENTE
        ]

        if not entregas_pendientes:
            campana.estado_id = ESTADO_ENVIADA
            db.commit()
            campanas_actualizadas += 1
            continue

        campana_enviados = 0
        campana_fallidos = 0
        campana_omitidos = 0

        for entrega in entregas_pendientes:
            if entrega.canal_id != 1 or not entrega.destinatario or not entrega.destinatario.email:
                omitidos += 1
                campana_omitidos += 1
                continue

            try:
                url_encuesta = _generar_url_encuesta(entrega.id)
                exito = await enviar_email(
                    destinatario_email=entrega.destinatario.email,
                    destinatario_nombre=entrega.destinatario.nombre or "Estimado/a",
                    asunto=f"Te invitamos a responder una encuesta: {campana.nombre}",
                    nombre_campana=campana.nombre,
                    nombre_empresa=nombre_empresa,
                    url_encuesta=url_encuesta,
                )

                if exito:
                    entrega.estado_id = ESTADO_ENVIADO
                    entrega.enviado_en = datetime.now(timezone.utc)
                    enviados += 1
                    campana_enviados += 1
                else:
                    entrega.estado_id = ESTADO_FALLIDO
                    fallidos += 1
                    campana_fallidos += 1
            except Exception:
                entrega.estado_id = ESTADO_FALLIDO
                fallidos += 1
                campana_fallidos += 1

        db.commit()

        # Verificar si todas las entregas se procesaron
        db.refresh(campana)
        pendientes_restantes = sum(1 for e in campana.entregas if e.estado_id == ESTADO_PENDIENTE)
        if pendientes_restantes == 0:
            campana.estado_id = ESTADO_ENVIADA
            db.commit()
            campanas_actualizadas += 1

        detalles.append({
            "campana_id": str(campana.id),
            "nombre": campana.nombre,
            "enviados": campana_enviados,
            "fallidos": campana_fallidos,
            "omitidos": campana_omitidos,
            "estado_final_id": campana.estado_id
        })

    return {
        "total_campanas_procesadas": total_procesadas,
        "enviados": enviados,
        "fallidos": fallidos,
        "omitidos": omitidos,
        "campanas_actualizadas": campanas_actualizadas,
        "detalles": detalles
    }
