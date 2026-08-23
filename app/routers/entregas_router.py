# app/routers/entregas_router.py
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from sqlalchemy.orm import Session, joinedload

from app.core.database import get_db
from app.core.security import get_current_user, validate_subscriber_access
from app.core.security import require_acceso_suscriptor_activo
from app.models.survey import CampanaEncuesta, EntregaEncuesta, PlantillaEncuesta, PreguntaEncuesta
from app.schemas.auth import TokenData
from app.schemas.entregas_schema import (
    EntregaCreate,
    EntregaUpdate,
    EntregaOut,
    EntregaDetailOut,
    EntregaPublicaOut,
)
from app.services.campanas_service import get_campana
from app.services.entregas_service import (
    create_bulk_entregas_audio,
    create_entrega,
    create_bulk_entregas_papel,   # ← helper para canal 4
    get_entrega,
    list_entregas,
    update_entrega,
    delete_entrega,
    mark_as_sent,
    mark_as_responded,
    get_entrega_by_destinatario,
    get_entrega_con_plantilla,
   
)
from app.services.respuestas_service import registrar_respuestas_publicas
from app.services.extractor import GeminiExtractorService
from app.core.constants import ESTADO_RESPONDIDO, ESTADO_PENDIENTE, ESTADO_ENVIADO

# ─────────────────────────── Routers ─────────────────────────────────────
router        = APIRouter(prefix="/campanas/{campana_id}/entregas", tags=["Entregas"])
public_router = APIRouter(prefix="/public/entregas",                tags=["Entregas Públicas"])


# ────────────────────── Helper de autorización ──────────────────────────
async def validate_campana_access(
    campana_id: UUID,
    token_data: TokenData,
    db: Session,
) -> None:
    campana = get_campana(db, campana_id)
    if not campana:
        raise HTTPException(404, "Campaña no encontrada")

    ok = await validate_subscriber_access(token_data, campana.suscriptor_id, db)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tiene permisos para acceder a esta campaña",
        )


from app.services.plan_limits_service import validate_entregas_limit, validate_canal_permission


# ───────────────────── Endpoints PRIVADOS (con auth) ─────────────────────
@router.post("", response_model=EntregaOut)
async def create_entrega_endpoint(
    campana_id: UUID,
    payload: EntregaCreate,
    token_data: TokenData = Depends(require_acceso_suscriptor_activo),
    db: Session = Depends(get_db),
):
    await validate_campana_access(campana_id, token_data, db)
    campana = get_campana(db, campana_id)
    if campana:
        validate_canal_permission(db, campana.suscriptor_id, campana.canal_id)
        validate_entregas_limit(db, campana.suscriptor_id, 1)
    return await create_entrega(db, campana_id, payload)


@router.post("/bulk", response_model=List[EntregaOut])
async def create_bulk_papel_endpoint(
    campana_id: UUID,
    cantidad: int = Query(..., ge=1, le=500),
    token_data: TokenData = Depends(require_acceso_suscriptor_activo),
    db: Session = Depends(get_db),
):
    """
    Genera *cantidad* entregas canal 4 (papel) sin destinatario.
    Sirve para imprimir formularios con QR.
    """
    await validate_campana_access(campana_id, token_data, db)

    campana = get_campana(db, campana_id)
    if not campana or campana.canal_id != 4:
        raise HTTPException(400, "La campaña debe ser de canal 4 (papel)")

    validate_canal_permission(db, campana.suscriptor_id, 4)
    validate_entregas_limit(db, campana.suscriptor_id, cantidad)

    return create_bulk_entregas_papel(db, campana_id, cantidad)


@router.get("", response_model=List[EntregaOut])
async def list_entregas_endpoint(
    campana_id: UUID,
    skip: int = Query(0, ge=0),
    limit: int = Query(800, le=1000),
    token_data: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    await validate_campana_access(campana_id, token_data, db)
    return list_entregas(db, campana_id, skip, limit)


@router.get("/{entrega_id}", response_model=EntregaDetailOut)
async def get_entrega_endpoint(
    campana_id: UUID,
    entrega_id: UUID,
    token_data: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    await validate_campana_access(campana_id, token_data, db)
    entrega = get_entrega(db, entrega_id)
    if not entrega or entrega.campana_id != campana_id:
        raise HTTPException(404, "Entrega no encontrada")
    return entrega


@router.patch("/{entrega_id}", response_model=EntregaOut)
async def update_entrega_endpoint(
    campana_id: UUID,
    entrega_id: UUID,
    payload: EntregaUpdate,
    token_data: TokenData = Depends(require_acceso_suscriptor_activo),
    db: Session = Depends(get_db),
):
    await validate_campana_access(campana_id, token_data, db)
    entrega = get_entrega(db, entrega_id)
    if not entrega or entrega.campana_id != campana_id:
        raise HTTPException(404, "Entrega no encontrada")
    return update_entrega(db, entrega_id, payload)


@router.delete("/{entrega_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_entrega_endpoint(
    campana_id: UUID,
    entrega_id: UUID,
    token_data: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    await validate_campana_access(campana_id, token_data, db)
    entrega = get_entrega(db, entrega_id)
    if not entrega or entrega.campana_id != campana_id:
        raise HTTPException(404, "Entrega no encontrada")
    delete_entrega(db, entrega_id)


# ---- cambios de estado ---------------------------------------------------
@router.post("/{entrega_id}/mark-sent", response_model=EntregaOut)
async def mark_as_sent_endpoint(
    campana_id: UUID,
    entrega_id: UUID,
    token_data: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    await validate_campana_access(campana_id, token_data, db)
    entrega = get_entrega(db, entrega_id)
    if not entrega or entrega.campana_id != campana_id:
        raise HTTPException(404, "Entrega no encontrada")
    return mark_as_sent(db, entrega_id)


@router.post("/{entrega_id}/mark-responded", response_model=EntregaOut)
async def mark_as_responded_endpoint(
    campana_id: UUID,
    entrega_id: UUID,
    token_data: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    await validate_campana_access(campana_id, token_data, db)
    entrega = get_entrega(db, entrega_id)
    if not entrega or entrega.campana_id != campana_id:
        raise HTTPException(404, "Entrega no encontrada")
    return mark_as_responded(db, entrega_id)


# ───────────────────── Endpoints PÚBLICOS (sin auth) ─────────────────────
@public_router.get("/{entrega_id}/plantilla", response_model=EntregaPublicaOut)
async def get_plantilla_entrega_publica(entrega_id: UUID, db: Session = Depends(get_db)):
    entrega = get_entrega_con_plantilla(db, entrega_id)
    if not entrega or not entrega.campana or not entrega.campana.plantilla:
        raise HTTPException(404, "Entrega o plantilla no encontrada")

    if entrega.estado_id == ESTADO_RESPONDIDO:
        raise HTTPException(400, "Esta encuesta ya ha sido respondida")

    return {
        "id": entrega.id,
        "plantilla": entrega.campana.plantilla,
        "destinatario": entrega.destinatario,
    }


@public_router.get("/{entrega_id}/plantilla-mapa")
async def get_plantilla_mapa_publico(entrega_id: UUID, db: Session = Depends(get_db)):
    """
    Devuelve preguntas + opciones con UUID (formato ligero para el micro-OCR).
    """
    entrega = get_entrega_con_plantilla(db, entrega_id)
    if not entrega or not entrega.campana or not entrega.campana.plantilla:
        raise HTTPException(404, "Entrega o plantilla no encontrada")

    if entrega.estado_id == ESTADO_RESPONDIDO:
        raise HTTPException(400, "Esta encuesta ya ha sido respondida")

    plantilla_id = entrega.campana.plantilla_id

    preguntas = (
        db.query(PreguntaEncuesta)
        .filter(PreguntaEncuesta.plantilla_id == plantilla_id)
        .order_by(PreguntaEncuesta.orden)
        .options(joinedload(PreguntaEncuesta.opciones))
        .all()
    )

    return {
        "entrega_id": str(entrega_id),
        "plantilla_id": str(plantilla_id),
        "preguntas": [
            {
                "id": str(p.id),
                "texto": p.texto,
                "orden": p.orden,
                "tipo_pregunta_id": p.tipo_pregunta_id,
                "opciones": [
                    {"id": str(o.id), "texto": o.texto, "valor": o.valor}
                    for o in p.opciones
                ],
            }
            for p in preguntas
        ],
    }


@public_router.post("/{entrega_id}/respuestas")
async def registrar_respuesta_publica(
    entrega_id: UUID,
    payload: Dict[str, Any],
    db: Session = Depends(get_db),
):
    """
    Recibe las respuestas del micro-OCR y las guarda en la BD.
    """
    try:
        resumen = await registrar_respuestas_publicas(db, entrega_id, payload)
    except HTTPException as e:
        raise e
    except Exception as exc:
        raise HTTPException(500, f"Error registrando respuestas: {exc}") from exc

    return {"status": "ok", "respuesta_id": str(resumen.id)}


def _build_plantilla_map(plantilla) -> dict:
    """Construye la estructura de plantilla de preguntas para guiar la extracción de Gemini."""
    if not plantilla:
        return {}
    return {
        "plantilla_id": str(plantilla.id),
        "nombre": plantilla.nombre,
        "preguntas": [
            {
                "pregunta_id": str(p.id),
                "texto": p.texto,
                "tipo_pregunta_id": p.tipo_pregunta_id,
                "opciones": [
                    {"opcion_id": str(o.id), "texto": o.texto}
                    for o in (p.opciones or [])
                ]
            }
            for p in (plantilla.preguntas or [])
        ]
    }


@public_router.post("/ocr")
async def extract_and_register_ocr_endpoint(
    file: UploadFile = File(...),
    entrega_id: Optional[UUID] = Form(None),
    db: Session = Depends(get_db)
):
    """
    Extrae y guarda respuestas a partir de una foto/escaneo de formulario de papel (Canal 4 - OCR).
    Usa Google Gemini Multimodal. Si no se provee entrega_id, intenta extraerlo del QR/encabezado.
    """
    image_bytes = await file.read()
    if not image_bytes:
        raise HTTPException(400, "El archivo de imagen está vacío")

    mime_type = file.content_type or "image/jpeg"
    extractor = GeminiExtractorService()

    target_id = entrega_id
    plantilla_map = {}

    if target_id:
        entrega = get_entrega_con_plantilla(db, target_id)
        if not entrega:
            raise HTTPException(404, f"Entrega {target_id} no encontrada")
        if entrega.estado_id == ESTADO_RESPONDIDO:
            raise HTTPException(400, "Esta encuesta ya ha sido respondida")
        plantilla_map = _build_plantilla_map(entrega.campana.plantilla)

    try:
        extracted_payload = extractor.extract_from_image(
            image_bytes=image_bytes,
            mime_type=mime_type,
            plantilla_map=plantilla_map
        )
    except Exception as exc:
        raise HTTPException(500, f"Error durante la extracción OCR con Gemini: {exc}") from exc

    if not target_id:
        raw_eid = extracted_payload.get("entrega_id")
        if not raw_eid:
            raise HTTPException(400, "No se proporcionó entrega_id ni fue detectado en la imagen por el OCR")
        try:
            target_id = UUID(raw_eid)
        except ValueError:
            raise HTTPException(400, f"El entrega_id detectado '{raw_eid}' no es un UUID válido")

        entrega = get_entrega_con_plantilla(db, target_id)
        if not entrega:
            raise HTTPException(404, f"Entrega {target_id} no encontrada")
        if entrega.estado_id == ESTADO_RESPONDIDO:
            raise HTTPException(400, "Esta encuesta ya ha sido respondida")

    resumen = await registrar_respuestas_publicas(db, target_id, extracted_payload)
    return {
        "status": "ok",
        "entrega_id": str(target_id),
        "respuesta_id": str(resumen.id),
        "respuestas": extracted_payload.get("respuestas_preguntas", [])
    }


@public_router.post("/{entrega_id}/audio")
async def extract_and_register_audio_endpoint(
    entrega_id: UUID,
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """
    Extrae, transcribe y guarda respuestas a partir de una grabación de audio (Canal 5 - Presencial/Voz).
    Usa Google Gemini Multimodal.
    """
    entrega = get_entrega_con_plantilla(db, entrega_id)
    if not entrega:
        raise HTTPException(404, f"Entrega {entrega_id} no encontrada")
    if entrega.estado_id == ESTADO_RESPONDIDO:
        raise HTTPException(400, "Esta encuesta ya ha sido respondida")

    audio_bytes = await file.read()
    if not audio_bytes:
        raise HTTPException(400, "El archivo de audio está vacío")

    mime_type = file.content_type or "audio/mp3"
    plantilla_map = _build_plantilla_map(entrega.campana.plantilla)

    extractor = GeminiExtractorService()
    try:
        extracted_payload = extractor.extract_from_audio(
            audio_bytes=audio_bytes,
            mime_type=mime_type,
            plantilla_map=plantilla_map
        )
    except Exception as exc:
        raise HTTPException(500, f"Error durante la extracción de audio con Gemini: {exc}") from exc

    resumen = await registrar_respuestas_publicas(db, entrega_id, extracted_payload)
    return {
        "status": "ok",
        "entrega_id": str(entrega_id),
        "respuesta_id": str(resumen.id),
        "transcripcion": extracted_payload.get("transcripcion", ""),
        "respuestas": extracted_payload.get("respuestas_preguntas", [])
    }


@public_router.get("/buscar", response_model=EntregaPublicaOut)
async def find_entrega_endpoint(
    email: Optional[str] = Query(None),
    telefono: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    if not email and not telefono:
        raise HTTPException(400, "Debe proporcionar email o teléfono")

    entrega = get_entrega_by_destinatario(db, email=email, telefono=telefono)
    if not entrega:
        raise HTTPException(404, "No se encontró ninguna entrega pendiente")

    if entrega.estado_id == ESTADO_RESPONDIDO:
        raise HTTPException(400, "La encuesta ya ha sido respondida")

    return entrega


@router.post("/bulk-audio", response_model=List[EntregaOut])
async def create_bulk_audio_endpoint(
    campana_id: UUID,
    cantidad: int = Query(..., ge=1, le=500),
    token_data: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    await validate_campana_access(campana_id, token_data, db)

    campana = get_campana(db, campana_id)
    if not campana or campana.canal_id != 5:
        raise HTTPException(400, "La campaña debe ser de canal 5 (audio grabado)")

    validate_canal_permission(db, campana.suscriptor_id, 5)
    validate_entregas_limit(db, campana.suscriptor_id, cantidad)

    return create_bulk_entregas_audio(db, campana_id, cantidad)



@public_router.get(
    "/audio",
    response_model=List[EntregaPublicaOut],
    summary="Lista las entregas de audio (canal 5) de esta campaña, con plantilla",
)
async def list_entregas_audio_campana(
    campana_id: UUID,
    db: Session = Depends(get_db),
):

    campana = get_campana(db, campana_id)
    if not campana or campana.canal_id != 5:
        raise HTTPException(
            status_code=400,
            detail="La campaña indicada no es de canal 5 (audio grabado)"
        )

    entregas = (
        db.query(EntregaEncuesta)
        .filter(EntregaEncuesta.campana_id == campana_id)
        .filter(EntregaEncuesta.estado_id != ESTADO_RESPONDIDO) 
        .options(
            joinedload(EntregaEncuesta.campana)
            .joinedload(CampanaEncuesta.plantilla)
            .joinedload(PlantillaEncuesta.preguntas)
            .joinedload(PreguntaEncuesta.opciones),
            joinedload(EntregaEncuesta.destinatario),
        )
        .all()
    )

    # Adaptamos a EntregaPublicaOut
    return [
        {
            "id":           e.id,
            "plantilla":    e.campana.plantilla,
        }
        for e in entregas
    ]