# app/services/ramificacion_service.py
import json
import logging
from typing import Dict, Any, List, Optional
from uuid import UUID
from sqlalchemy.orm import Session

from app.models.survey import (
    PlantillaEncuesta, PreguntaEncuesta, ConversacionEncuesta, EntregaEncuesta
)
from app.models.regla_ramificacion import ReglaRamificacion
from app.services.gemini_service import call_gemini_text

logger = logging.getLogger(__name__)

def detectar_sentimiento_o_baja_calificacion(texto_respuesta: str, puntuacion: Optional[float] = None) -> bool:
    """
    Detecta si una respuesta tiene sentimiento muy negativo o calificación baja (≤ 2 o palabras clave de insatisfacción)
    para disparar la pregunta de seguimiento generativa (RF17b).
    """
    if puntuacion is not None and puntuacion <= 2.0:
        return True

    texto_lower = (texto_respuesta or "").lower()
    palabras_negativas = [
        "pésimo", "pesimo", "horrible", "terrible", "muy mala", "muy malo",
        "desastre", "estafa", "inútil", "inutil", "nunca más", "nunca mas",
        "decepcionante", "peor", "molesto", "enojado", "furioso", "asco"
    ]
    return any(p in texto_lower for p in palabras_negativas)

async def generar_pregunta_seguimiento(
    contexto_encuesta: str,
    respuesta_negativa: str
) -> str:
    """
    Invoca a Gemini para formular UNA única pregunta abierta de seguimiento empática y contextual (RF17b).
    """
    prompt = f"""
Eres un asistente de investigación de experiencia de usuario.
El usuario ha respondido de forma insatisfecha o muy negativa a una encuesta.

Contexto de la encuesta: {contexto_encuesta}
Respuesta del usuario: "{respuesta_negativa}"

Genera UNA SOLA pregunta de seguimiento abierta, empática y profesional para comprender
específicamente qué falló o qué podríamos mejorar.
Devuelve ÚNICAMENTE la pregunta, sin introducciones ni comillas.
"""
    try:
        pregunta = await call_gemini_text(prompt=prompt)
        return pregunta.strip().strip('"') if pregunta else "¿Podrías detallarnos qué aspecto específico de tu experiencia podemos mejorar?"
    except Exception as e:
        logger.warning("Error generando pregunta de seguimiento con Gemini: %s", e)
        return "¿Podrías detallarnos qué aspecto específico de tu experiencia podemos mejorar?"

async def seleccionar_siguiente_pregunta_adaptativa(
    db: Session,
    plantilla_id: UUID,
    pregunta_actual_id: Optional[UUID],
    respuesta_actual_texto: str,
    historial: List[Dict[str, Any]],
    preguntas_respondidas_ids: List[str]
) -> Dict[str, Any]:
    """
    Motor de ramificación adaptativa (RF17).
    Gemini evalúa el objetivo y el banco de preguntas candidatas, y devuelve
    estrictamente el ID de la siguiente pregunta del banco o la señal de fin de encuesta.
    """
    # 1. Obtener todas las preguntas de la plantilla
    todas_preguntas = (
        db.query(PreguntaEncuesta)
        .filter(PreguntaEncuesta.plantilla_id == plantilla_id)
        .order_by(PreguntaEncuesta.orden.asc())
        .all()
    )

    plantilla = db.query(PlantillaEncuesta).filter_by(id=plantilla_id).first()
    objetivo_encuesta = (plantilla.descripcion or plantilla.nombre) if plantilla else "Medir satisfacción"

    # 2. Filtrar banco de candidatas (excluir ya respondidas)
    candidatas = [p for p in todas_preguntas if str(p.id) not in preguntas_respondidas_ids and p.id != pregunta_actual_id]

    if not candidatas:
        return {
            "siguiente_pregunta_id": None,
            "fin_encuesta": True,
            "justificacion": "No quedan más preguntas en el banco disponible."
        }

    # 3. Revisar si existe una regla de ramificación determinística configurada en BD
    if pregunta_actual_id:
        reglas = (
            db.query(ReglaRamificacion)
            .filter(
                ReglaRamificacion.plantilla_id == plantilla_id,
                ReglaRamificacion.pregunta_origen_id == pregunta_actual_id
            )
            .order_by(ReglaRamificacion.orden_prioridad.asc())
            .all()
        )
        for regla in reglas:
            condicion = regla.condicion_semantica.lower().strip()
            if condicion in respuesta_actual_texto.lower():
                if regla.es_fin_encuesta:
                    return {"siguiente_pregunta_id": None, "fin_encuesta": True, "justificacion": "Regla determinística de fin activada"}
                if regla.pregunta_destino_id:
                    return {"siguiente_pregunta_id": str(regla.pregunta_destino_id), "fin_encuesta": False, "justificacion": "Regla determinística coincidente"}

    # 4. Construir prompt estructurado para Gemini
    banco_str = "\n".join([f"- ID: {p.id} | Pregunta: '{p.texto}' (Tipo: {p.tipo_pregunta_id})" for p in candidatas])
    historial_str = "\n".join([f"P: {h.get('pregunta', '')} -> R: {h.get('respuesta', '')}" for h in historial[-4:]])

    prompt = f"""
Actúa como un motor de ramificación de encuestas adaptativas.
Tu objetivo es elegir la MEJOR siguiente pregunta del BANCO DE CANDIDATAS basándote en la última respuesta y el historial.

Objetivo de la encuesta: {objetivo_encuesta}
Historial reciente:
{historial_str}

Última respuesta del usuario: "{respuesta_actual_texto}"

BANCO DE PREGUNTAS CANDIDATAS (Solo puedes elegir una de estas o finalizar):
{banco_str}

REGLA ESTRICTA DE SALIDA:
Devuelve ÚNICAMENTE un JSON con esta estructura exacta, sin texto adicional:
{{
  "siguiente_pregunta_id": "UUID_DE_LA_PREGUNTA_ELEGIDA_DEL_BANCO" o null,
  "fin_encuesta": true o false,
  "justificacion": "Explicación concisa"
}}
"""
    try:
        raw_res = await call_gemini_text(prompt=prompt)
        clean_json = raw_res.strip()
        if "```json" in clean_json:
            clean_json = clean_json.split("```json")[1].split("```")[0].strip()
        elif "```" in clean_json:
            clean_json = clean_json.split("```")[1].split("```")[0].strip()

        parsed = json.loads(clean_json)
        chosen_id = parsed.get("siguiente_pregunta_id")

        # Verificación estricta de pertenencia al banco
        candidatas_ids = {str(p.id) for p in candidatas}
        if chosen_id and str(chosen_id) in candidatas_ids:
            return {
                "siguiente_pregunta_id": str(chosen_id),
                "fin_encuesta": False,
                "justificacion": parsed.get("justificacion", "Seleccionada por relevancia semántica")
            }
        elif parsed.get("fin_encuesta") is True or not chosen_id:
            return {
                "siguiente_pregunta_id": None,
                "fin_encuesta": True,
                "justificacion": parsed.get("justificacion", "Fin de encuesta determinado por el modelo")
            }
    except Exception as e:
        logger.warning("Fallback en ramificación adaptativa: %s", e)

    # Fallback determinístico seguro: siguiente pregunta en orden secuencial del banco
    primer_candidata = candidatas[0]
    return {
        "siguiente_pregunta_id": str(primer_candidata.id),
        "fin_encuesta": False,
        "justificacion": "Selección secuencial por fallback seguro"
    }
