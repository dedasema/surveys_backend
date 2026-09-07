# app/services/agente_service.py
import time
import json
import logging
from typing import Optional, Dict, Any
from uuid import UUID
from sqlalchemy.orm import Session

from app.models.survey import CampanaEncuesta, RespuestaEncuesta
from app.models.agente_decision import AgenteDecision
from app.services.gemini_service import call_gemini_text

logger = logging.getLogger(__name__)

HERRAMIENTAS_DISPONIBLES = [
    {
        "nombre": "escalar_caso_soporte",
        "descripcion": "Escala de inmediato un caso crítico a atención al cliente o soporte técnico ante quejas graves o insatisfacción severa.",
        "parametros": ["prioridad", "departamento", "motivo", "ticket_externo"]
    },
    {
        "nombre": "enviar_recordatorio_encuesta",
        "descripcion": "Programa un recordatorio cortés para destinatarios que aún no han interactuado tras cierto periodo de inactividad.",
        "parametros": ["canal_preferido", "plantilla_tono", "dias_inactividad"]
    },
    {
        "nombre": "marcar_para_revision_urgente",
        "descripcion": "Marca la respuesta o entrega para auditoría manual por parte de un operador humano.",
        "parametros": ["motivo", "criticidad"]
    }
]

async def evaluar_evento_con_agente(
    db: Session,
    campana_id: UUID,
    trigger_evento: str,
    respuesta_id: Optional[UUID] = None,
    contexto_adicional: Optional[Dict[str, Any]] = None
) -> AgenteDecision:
    """
    Agente autónomo con Function Calling y Registro de Decisiones (RF25).
    Evalúa el evento disparador y contexto de la encuesta, decide y razona la herramienta
    a invocar y persiste la traza de auditoría con tiempo de ejecución.
    """
    start_time = time.time()

    campana = db.query(CampanaEncuesta).filter_by(id=campana_id).first()
    campana_nombre = campana.nombre if campana else "Campaña"

    tools_str = json.dumps(HERRAMIENTAS_DISPONIBLES, indent=2, ensure_ascii=False)
    contexto_str = json.dumps(contexto_adicional or {}, ensure_ascii=False)

    prompt = f"""
Eres el Agente Autónomo de Automatización de SurveySaaS.
Tu objetivo es analizar un evento de negocio ocurrido en una campaña de encuestas y decidir qué herramienta ejecutar.

Campaña: '{campana_nombre}' (ID: {campana_id})
Evento disparador: "{trigger_evento}"
Contexto complementario: {contexto_str}

HERRAMIENTAS DISPONIBLES:
{tools_str}

INSTRUCCIONES DE SALIDA:
Analiza el caso, razona tu decisión paso a paso y devuelve ÚNICAMENTE un JSON con esta estructura exacta:
{{
  "tool_ejecutada": "nombre_de_la_herramienta_elegida",
  "parametros": {{ ...objeto con los parámetros coherentes para la herramienta... }},
  "razonamiento_ia": "Explicación detallada de por qué se eligió esta acción y qué impacto se espera."
}}
"""
    tool_elegida = "marcar_para_revision_urgente"
    parametros_usados = {"motivo": "Revisión general requerida por evento", "criticidad": "moderada"}
    razonamiento = "Se programa revisión preventiva estándar para el evento recibido."
    estado = "ejecutado"

    try:
        raw_res = await call_gemini_text(prompt=prompt)
        clean = raw_res.strip()
        if "```json" in clean:
            clean = clean.split("```json")[1].split("```")[0].strip()
        elif "```" in clean:
            clean = clean.split("```")[1].split("```")[0].strip()

        data = json.loads(clean)
        t_nombre = data.get("tool_ejecutada")
        if any(h["nombre"] == t_nombre for h in HERRAMIENTAS_DISPONIBLES):
            tool_elegida = t_nombre
            parametros_usados = data.get("parametros", {})
            razonamiento = data.get("razonamiento_ia", razonamiento)
    except Exception as e:
        logger.warning("Fallback en evaluación de agente autónomo: %s", e)
        # Regla heurística de fallback
        if "insatisfacción" in trigger_evento.lower() or "negativo" in trigger_evento.lower() or "pésimo" in trigger_evento.lower():
            tool_elegida = "escalar_caso_soporte"
            parametros_usados = {
                "prioridad": "alta",
                "departamento": "Atención al Cliente",
                "motivo": "Respuesta con queja severa detectada en encuesta",
                "ticket_externo": False
            }
            razonamiento = "El encuestado manifestó insatisfacción crítica; se deriva a soporte de acuerdo a las políticas de contención."
        elif "inactividad" in trigger_evento.lower() or "recordatorio" in trigger_evento.lower():
            tool_elegida = "enviar_recordatorio_encuesta"
            parametros_usados = {
                "canal_preferido": "gmail",
                "plantilla_tono": "cordial_breve",
                "dias_inactividad": 3
            }
            razonamiento = "Transcurrió el umbral de entrega sin apertura; se activa recordatorio automático."

    execution_ms = max(1, int((time.time() - start_time) * 1000))

    decision = AgenteDecision(
        campana_id=campana_id,
        campana_nombre=campana_nombre,
        trigger_evento=trigger_evento,
        respuesta_id=respuesta_id,
        tool_ejecutada=tool_elegida,
        parametros=parametros_usados,
        razonamiento_ia=razonamiento,
        estado=estado,
        tiempo_ejecucion_ms=execution_ms
    )
    db.add(decision)
    db.commit()
    db.refresh(decision)

    # Emitir evento por WebSocket (RF24)
    try:
        from app.services.websocket_manager import ws_manager
        await ws_manager.broadcast(
            "decision_agente",
            {
                "id": str(decision.id),
                "campana_id": str(decision.campana_id),
                "campana_nombre": decision.campana_nombre,
                "trigger_evento": decision.trigger_evento,
                "tool_ejecutada": decision.tool_ejecutada,
                "parametros": decision.parametros or {},
                "razonamiento_ia": decision.razonamiento_ia,
                "estado": decision.estado
            },
            campana_id=str(decision.campana_id)
        )
    except Exception as e_ws:
        logger.warning("Fallo al emitir decisión de agente por WebSocket: %s", e_ws)

    return decision
