# app/services/copilot_service.py
import json
import time
import logging
from typing import Dict, Any, List, Optional
from uuid import UUID
from sqlalchemy.orm import Session

from app.services.mcp import mcp_registry, ActorContext
from app.services.gemini_service import call_gemini_chat_with_tools, call_gemini_text
from app.services.audit_service import registrar_auditoria
from app.models.agente_decision import AgenteDecision
from app.models.survey import CampanaEncuesta

logger = logging.getLogger(__name__)

COPILOT_SYSTEM_INSTRUCTION_BASE = """Eres el Copiloto Inteligente de Analítica y Operaciones de SurveySaaS.
Estás asistiendo a un usuario autenticado con rol '{rol}' de la empresa '{empresa_nombre}'.
Tu objetivo es analizar resultados de encuestas, interpretar métricas, alertar sobre fraudes y recomendar mejoras.

DIRECTRICES CLAVE:
1. NUNCA inventes datos, números ni estadísticas. Si te consultan sobre métricas, campañas, resumen o alertas, UTILIZA SIEMPRE las herramientas MCP correspondientes.
2. Si ejecutaste una herramienta, presenta los datos de forma estructurada con viñetas, porcentajes claros y conclusiones accionables.
3. Sé profesional, analítico y conciso.
4. Si el usuario te saluda o hace una pregunta conceptual sobre diseño de encuestas o mejores prácticas, respondé directamente con calidez y rigor técnico.
"""

async def procesar_mensaje_copilot(
    db: Session,
    actor: ActorContext,
    mensaje: str,
    historial: Optional[List[Dict[str, str]]] = None,
    campana_id: Optional[UUID] = None
) -> Dict[str, Any]:
    """
    Orquesta la conversación del Copiloto web invocando herramientas MCP autorizadas
    y sintetizando la respuesta final con Gemini.
    """
    empresa_nombre = actor.nombre or "Empresa Suscriptora"
    system_instruction = COPILOT_SYSTEM_INSTRUCTION_BASE.format(
        rol=actor.role,
        empresa_nombre=empresa_nombre
    )

    tools_gemini = mcp_registry.list_tools_for_gemini(actor)
    tools_usadas: List[Dict[str, Any]] = []
    acciones_sugeridas: List[str] = []

    # Construir contexto con historial reciente (máximo 4 mensajes previos)
    conversacion_prompt = ""
    if historial:
        conversacion_prompt += "Historial previo de la conversación:\n"
        for h in historial[-4:]:
            sender = h.get("sender", "user")
            text = h.get("text", "")
            conversacion_prompt += f"- {sender}: {text}\n"
        conversacion_prompt += "\n"
    conversacion_prompt += f"Mensaje actual del usuario: {mensaje}"

    start_time = time.time()
    respuesta_texto = ""

    try:
        # 1. Consultar a Gemini con Tools
        gemini_res = await call_gemini_chat_with_tools(
            system_instruction=system_instruction,
            user_message=conversacion_prompt,
            tools=tools_gemini
        )

        # 2. Si Gemini solicita invocar una Tool
        if gemini_res.get("type") == "tool_call":
            tool_name = gemini_res.get("name")
            tool_args = gemini_res.get("args") or {}

            # Si el usuario pasó campana_id de contexto y la tool la requiere pero el LLM no la puso
            if campana_id and "campana_id" not in tool_args and tool_name == "obtener_metricas_campana":
                tool_args["campana_id"] = str(campana_id)

            logger.info("Copilot ejecutando tool MCP '%s' con args: %s", tool_name, tool_args)
            t_exec_start = time.time()
            tool_result = await mcp_registry.execute_tool(tool_name, tool_args, actor, db)
            t_exec_ms = int((time.time() - t_exec_start) * 1000)

            tools_usadas.append({
                "tool": tool_name,
                "arguments": tool_args,
                "result_summary": str(tool_result.get("data"))[:200]
            })

            # Registrar auditoría de ejecución
            registrar_auditoria(
                db=db,
                accion="COPILOT_TOOL_EXECUTION",
                modulo="COPILOT_MCP",
                usuario_id=actor.user_id,
                usuario_email=actor.email,
                rol=actor.role,
                suscriptor_id=actor.suscriptor_id,
                detalles={
                    "tool": tool_name,
                    "arguments": tool_args,
                    "success": tool_result["success"],
                    "ejecucion_ms": t_exec_ms
                }
            )

            # Si la consulta aplica a una campaña específica, registrar en AgenteDecision
            target_campana_id = None
            if "campana_id" in tool_args:
                try:
                    target_campana_id = UUID(str(tool_args["campana_id"]))
                except Exception:
                    pass
            elif campana_id:
                target_campana_id = campana_id

            if target_campana_id:
                try:
                    campana_obj = db.query(CampanaEncuesta).filter_by(id=target_campana_id).first()
                    campana_nombre_str = campana_obj.nombre if campana_obj else "Campaña"
                    decision = AgenteDecision(
                        campana_id=target_campana_id,
                        campana_nombre=campana_nombre_str,
                        trigger_evento=f"Consulta Copilot: {mensaje[:200]}",
                        tool_ejecutada=tool_name,
                        parametros=tool_args,
                        razonamiento_ia=f"Invocado automáticamente por Copilot para responder '{mensaje[:100]}'",
                        estado="ejecutado" if tool_result["success"] else "fallido",
                        tiempo_ejecucion_ms=t_exec_ms
                    )
                    db.add(decision)
                    db.commit()
                except Exception as e_dec:
                    db.rollback()
                    logger.warning("No se pudo registrar AgenteDecision: %s", e_dec)

            # 3. Síntesis final de la respuesta con los datos obtenidos
            prompt_sintesis = (
                f"El usuario preguntó: \"{mensaje}\"\n\n"
                f"Se ejecutó la herramienta MCP '{tool_name}' con parámetros {json.dumps(tool_args)}.\n"
                f"El resultado obtenido de la plataforma fue:\n"
                f"{json.dumps(tool_result.get('data') if tool_result.get('success') else {'error': tool_result.get('error')}, indent=2, ensure_ascii=False)}\n\n"
                f"Por favor redacta la respuesta final para el usuario analizando y explicando estos datos de forma clara, profesional y con viñetas cuando corresponda."
            )
            respuesta_texto = await call_gemini_text(
                prompt=prompt_sintesis,
                system_instruction=system_instruction
            )
            if not respuesta_texto:
                respuesta_texto = f"He consultado los datos con la herramienta `{tool_name}`: {json.dumps(tool_result.get('data'), ensure_ascii=False)}"

        else:
            # Respuesta textual directa sin invocación de tools
            respuesta_texto = gemini_res.get("text", "")

    except Exception as e:
        logger.warning("Fallo en orquestación Gemini Copilot: %s. Aplicando fallback determinista.", e)
        # Fallback determinista en caso de que Gemini esté en pausa o sin cuota
        respuesta_texto, tools_usadas = await _ejecutar_fallback_deterministico(
            db=db,
            actor=actor,
            mensaje=mensaje,
            campana_id=campana_id
        )

    # Generar acciones sugeridas según contexto
    if "campaña" in mensaje.lower() or "campanas" in mensaje.lower():
        acciones_sugeridas = ["Ver campañas activas", "Crear nueva campaña", "Auditar fraudes"]
    elif "fraude" in mensaje.lower() or "alerta" in mensaje.lower():
        acciones_sugeridas = ["Revisar cola de fraude", "Ver respuestas sospechosas"]
    elif "pregunta" in mensaje.lower():
        acciones_sugeridas = ["Copiar preguntas a plantilla", "Generar preguntas para WhatsApp"]
    else:
        acciones_sugeridas = ["Ver resumen de métricas", "Listar campañas activas", "Consultar alertas de fraude"]

    return {
        "answer": respuesta_texto,
        "tools_used": tools_usadas,
        "suggested_actions": acciones_sugeridas
    }


async def _ejecutar_fallback_deterministico(
    db: Session,
    actor: ActorContext,
    mensaje: str,
    campana_id: Optional[UUID] = None
) -> tuple[str, List[Dict[str, Any]]]:
    """
    Fallback seguro y robusto en caso de caída o saturación temporal de cuota de la API de LLM.
    Identifica la intención del usuario y ejecuta la tool MCP adecuada directamente.
    """
    msg_lower = mensaje.lower()
    tools_usadas = []

    if any(k in msg_lower for k in ["resumen", "estado", "general", "cuenta", "metricas generales"]):
        res = await mcp_registry.execute_tool("obtener_resumen_empresa", {}, actor, db)
        tools_usadas.append({"tool": "obtener_resumen_empresa", "arguments": {}, "result_summary": "Resumen general"})
        if res["success"]:
            d = res["data"]
            texto = (
                f"### Resumen de tu Empresa ({d.get('empresa_nombre')}):\n"
                f"- **Plan Contratado:** {d.get('plan_actual')}\n"
                f"- **Plantillas creadas:** {d.get('total_plantillas')}\n"
                f"- **Campañas totales:** {d.get('total_campanas')}\n"
                f"- **Respuestas recolectadas:** {d.get('total_respuestas')}\n"
                f"- **Operadores activos:** {d.get('total_operadores')}"
            )
            return texto, tools_usadas

    if any(k in msg_lower for k in ["campaña", "campanas", "listar"]):
        res = await mcp_registry.execute_tool("listar_campanas_empresa", {"limite": 5}, actor, db)
        tools_usadas.append({"tool": "listar_campanas_empresa", "arguments": {"limite": 5}, "result_summary": "Listado campañas"})
        if res["success"]:
            d = res["data"]
            campanas = d.get("campanas", [])
            if not campanas:
                return "Actualmente no tenés campañas registradas. Podés crear una desde la sección de Campañas.", tools_usadas
            lineas = [f"- **{c['nombre']}** (ID: `{c['id']}`) — {c['total_respuestas']} respuestas de {c['total_entregas']} envíos" for c in campanas]
            return "### Tus campañas más recientes:\n" + "\n".join(lineas), tools_usadas

    if any(k in msg_lower for k in ["fraude", "alerta", "sospech"]) :
        res = await mcp_registry.execute_tool("consultar_alertas_fraude", {"limite": 5}, actor, db)
        tools_usadas.append({"tool": "consultar_alertas_fraude", "arguments": {"limite": 5}, "result_summary": "Alertas fraude"})
        if res["success"]:
            d = res["data"]
            total = d.get("total_alertas", 0)
            return f"Actualmente registrás **{total}** alertas de fraude detectadas en tus encuestas.", tools_usadas

    if any(k in msg_lower for k in ["pregunta", "suger", "recomiend"]):
        res = await mcp_registry.execute_tool("sugerir_preguntas_encuesta", {"objetivo": "Satisfacción de clientes"}, actor, db)
        tools_usadas.append({"tool": "sugerir_preguntas_encuesta", "arguments": {"objetivo": "Satisfacción de clientes"}, "result_summary": "Sugerencias"})
        if res["success"]:
            d = res["data"]
            preguntas = [f"{p['orden']}. {p['texto']} *({p['tipo']})*" for p in d.get("preguntas", [])]
            return "### Preguntas sugeridas para medir satisfacción:\n" + "\n".join(preguntas), tools_usadas

    return (
        "Hola, soy tu Copiloto Inteligente de SurveySaaS. Puedo ayudarte a consultar el resumen de tu empresa, "
        "revisar el estado de tus campañas, analizar métricas de rendimiento, inspeccionar alertas de fraude "
        "o generar sugerencias de preguntas para tus nuevas encuestas. ¿Qué te gustaría consultar?",
        []
    )
