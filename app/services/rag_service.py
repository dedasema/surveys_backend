# app/services/rag_service.py
import logging
from typing import Optional, Dict, Any, List
from uuid import UUID
from sqlalchemy.orm import Session

from app.models.survey import (
    RespuestaPregunta, RespuestaEncuesta, EntregaEncuesta, CampanaEncuesta
)
from app.models.rag_consulta import RagConsulta
from app.services.embedding_service import generar_embedding, similitud_coseno
from app.services.gemini_service import call_gemini_text

logger = logging.getLogger(__name__)

async def consultar_asistente_rag(
    db: Session,
    pregunta: str,
    campana_id: Optional[UUID] = None
) -> Dict[str, Any]:
    """
    Asistente RAG con búsqueda semántica sobre respuestas y fundamentación con citas directas (RF26).
    """
    if not pregunta or not pregunta.strip():
        return {
            "respuesta": "Por favor escribe una consulta válida para analizar.",
            "fuentes_citadas": []
        }

    # 1. Obtener respuestas candidatas de la BD
    query = (
        db.query(RespuestaPregunta)
        .join(RespuestaEncuesta, RespuestaPregunta.respuesta_id == RespuestaEncuesta.id)
        .join(EntregaEncuesta, RespuestaEncuesta.entrega_id == EntregaEncuesta.id)
        .join(CampanaEncuesta, EntregaEncuesta.campana_id == CampanaEncuesta.id)
        .filter(
            RespuestaPregunta.texto.isnot(None),
            RespuestaPregunta.texto != ""
        )
    )
    if campana_id:
        query = query.filter(EntregaEncuesta.campana_id == campana_id)

    items = query.order_by(RespuestaEncuesta.recibido_en.desc()).limit(60).all()

    # 2. Embedding de la pregunta y cálculo de similitud
    emb_pregunta = await generar_embedding(pregunta)

    candidatos_con_score = []
    for item in items:
        t = (item.texto or "").strip()
        if len(t) < 5:
            continue

        vec = item.embedding
        if vec is None or len(vec) != 768:
            vec = await generar_embedding(t)
            try:
                item.embedding = vec
            except Exception:
                pass

        sim = similitud_coseno(emb_pregunta, vec)
        candidatos_con_score.append((sim, item))

    # Ordenar por mayor similitud semántica
    candidatos_con_score.sort(key=lambda x: x[0], reverse=True)
    top_candidatos = candidatos_con_score[:4]

    fuentes_citadas: List[Dict[str, Any]] = []
    contexto_lineas: List[str] = []

    for sim, rp in top_candidatos:
        resp = rp.respuesta
        entrega = resp.entrega if resp else None
        camp = entrega.campana if entrega else None

        canal_nombre = "web"
        if entrega and entrega.canal_id == 1:
            canal_nombre = "gmail"
        elif entrega and entrega.canal_id == 2:
            canal_nombre = "voz"
        elif entrega and entrega.canal_id == 3:
            canal_nombre = "ocr"

        fecha_str = resp.recibido_en.strftime("%Y-%m-%d") if (resp and resp.recibido_en) else "Reciente"
        camp_nombre = camp.nombre if camp else "Campaña General"

        fuentes_citadas.append({
            "id": str(rp.id),
            "tipo": "respuesta",
            "canal": canal_nombre,
            "campana": camp_nombre,
            "fragmento": rp.texto[:250],
            "similitud_score": round(max(0.1, sim), 2),
            "fecha": fecha_str
        })

        contexto_lineas.append(
            f"[{len(contexto_lineas) + 1}] (Canal: {canal_nombre}, Campaña: {camp_nombre}, Fecha: {fecha_str}): \"{rp.texto}\""
        )

    # 3. Construir prompt RAG para Gemini
    contexto_str = "\n".join(contexto_lineas) if contexto_lineas else "No se encontraron respuestas registradas aún."

    prompt = f"""
Eres un asistente de inteligencia artificial avanzado para SurveySaaS especializado en RAG (Retrieval-Augmented Generation).
Tu tarea es responder a la consulta del usuario basándote ESTRICTAMENTE en el siguiente contexto de feedback y encuestas recopiladas.

PREGUNTA DEL USUARIO:
"{pregunta}"

EVIDENCIA Y CITAS DEL SISTEMA:
{contexto_str}

REGLAS DE RESPUESTA:
1. Responde de forma concisa, analítica y fundamentada.
2. Si la evidencia no responde completamente a la pregunta, dilo con honestidad.
3. Menciona los hallazgos clave y patrones observados en el feedback.
"""
    try:
        respuesta_texto = await call_gemini_text(prompt=prompt)
        if not respuesta_texto:
            respuesta_texto = "Con base en las respuestas analizadas, se identifican las opiniones detalladas en las fuentes citadas a continuación."
    except Exception as e:
        logger.warning("Fallback en RAG con Gemini: %s", e)
        respuesta_texto = "Con base en las respuestas analizadas, se identifican las opiniones detalladas en las fuentes citadas a continuación."

    # 4. Guardar historial en la base de datos
    consulta_record = RagConsulta(
        campana_id=campana_id,
        pregunta=pregunta,
        respuesta=respuesta_texto.strip(),
        fuentes_citadas=fuentes_citadas
    )
    db.add(consulta_record)
    db.commit()
    db.refresh(consulta_record)

    return {
        "id": str(consulta_record.id),
        "respuesta": consulta_record.respuesta,
        "fuentes_citadas": fuentes_citadas
    }
