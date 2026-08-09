# app/services/chat_service.py
"""
Chat GPT para SurveySaaS  –  OpenAI v1  (sin embeddings)
─────────────────────────────────────────────────────────
• Conversa normalmente y sólo pregunta la sección si de verdad falta.
• Si el usuario responde “plantillas”, “campañas”, etc., lo tomamos como sección.
• Function-calling: create_template  →  inserta plantilla + preguntas/opciones.
"""

from __future__ import annotations
import os, json
from uuid import UUID
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.schemas.plantillas_schema import PlantillaCreate
from app.schemas.preguntas_schema import PreguntaCreate, OpcionCreate
from app.services.plantillas_service import create_plantilla
from app.services.preguntas_service import create_pregunta
from app.services.opciones_service import create_opcion
from app.models.cuenta_usuario import CuentaUsuario

# ─────────────────── Config ─────────────────── #
OPENAI_MODEL   = os.getenv("OPENAI_MODEL", "gpt-4o")  

_client = None

def get_openai_client():
    global _client
    if _client is None:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("Debes definir OPENAI_API_KEY en .env")
        from openai import OpenAI
        _client = OpenAI(api_key=api_key)
    return _client

GLOBAL_CONTEXT = """
Eres el asistente virtual de SurveySaaS.
Secciones principales: Plantillas, Campañas, Destinatarios, Entregas, Respuestas.
Responde siempre en español. Si no recibes ‘route/section’ y lo necesitas,
pregunta UNA sola vez: «¿En qué parte de la aplicación estás?».
Si recibes el bloque “🧭 Contexto de pantalla” NO vuelvas a preguntar.
Cuando ejecutes una función, explica primero lo que harás y luego confirma.
"""

# ─────────────────── Tools (function-calling) ─────────────────── #
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "create_template",
            "description": "Crea una plantilla con preguntas y opciones",
            "parameters": {
                "type": "object",
                "properties": {
                    "nombre":      {"type": "string"},
                    "descripcion": {"type": "string"},
                    "preguntas": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "orden":            {"type": "integer"},
                                "texto":            {"type": "string"},
                                "tipo_pregunta_id": {"type": "integer"},
                                "obligatorio":      {"type": "boolean"},
                                "opciones": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "nullable": True,
                                },
                            },
                            "required": ["texto", "tipo_pregunta_id", "obligatorio"],
                        },
                    },
                },
                "required": ["nombre", "preguntas"],
            },
        },
    }
]

# ─────────────────── Helpers ─────────────────── #
_SECCIONES = {"plantillas", "campañas", "destinatarios", "entregas", "respuestas", "dashboard"}

def _suscriptor_id(token_data, db: Session) -> UUID:
    """Devuelve el suscriptor_id según el rol del token."""
    if token_data.role == "empresa":
        return UUID(token_data.sub)
    user = db.query(CuentaUsuario).get(UUID(token_data.sub))
    if not user:
        raise RuntimeError("Operador no encontrado")
    return user.suscriptor_id

def _build_msgs(user_msg: str, ctx: Optional[dict]) -> List[dict]:
    """
    Crea la lista de mensajes para OpenAI:
    • GLOBAL_CONTEXT
    • 🧭 Contexto de pantalla   (si llega o si deducimos la sección)
    • Mensaje del usuario
    """
    if not ctx:
        maybe = user_msg.strip().lower()
        if maybe in _SECCIONES:
            ctx = {"route": "N/A", "section": maybe}

    msgs = [{"role": "system", "content": GLOBAL_CONTEXT}]
    if ctx:
        pantalla = f"{ctx.get('section')} ({ctx.get('route')})"
        msgs.append({"role": "system", "content": f"🧭 Contexto de pantalla: {pantalla}"})
    msgs.append({"role": "user", "content": user_msg})
    return msgs

def _crear_plantilla(db: Session, suscriptor_id: UUID, args: Dict[str, Any]) -> Dict[str, Any]:
    """Inserta plantilla + preguntas/opciones. Devuelve objeto y log."""
    plantilla = create_plantilla(
        db,
        PlantillaCreate(
            nombre=args["nombre"],
            descripcion=args.get("descripcion"),
        ),
        suscriptor_id,
    )

    log = [f"Plantilla creada (id={plantilla.id})"]

    for idx, p in enumerate(args["preguntas"], 1):
        pregunta = create_pregunta(
            db,
            plantilla.id,
            PreguntaCreate(
                orden=p.get("orden"),
                texto=p["texto"],
                tipo_pregunta_id=p["tipo_pregunta_id"],
                obligatorio=p["obligatorio"],
            ),
        )
        log.append(f" – Pregunta {idx}: id={pregunta.id}")

        for j, texto in enumerate(p.get("opciones") or [], 1):
            opcion = create_opcion(db, pregunta.id, OpcionCreate(texto=texto))
            log.append(f"   • Opción {j}: id={opcion.id}")

    return {"plantilla": plantilla, "action_log": log}

# ─────────────────── Entrada principal ─────────────────── #
async def chat_completion(
    db: Session,
    token_data,
    message: str,
    context: Optional[dict] = None,
    history: Optional[List[dict]] = None,   # ← si quieres pasar historial
) -> Dict[str, Any]:
    """
    Devuelve:
        answer      -> texto al usuario
        action_log  -> acciones ejecutadas para transparencia
    """
    gemini_key = os.getenv("GEMINI_API_KEY")
    if gemini_key and gemini_key.strip():
        from app.services.gemini_service import call_gemini_chat_with_tools
        try:
            sys_inst = GLOBAL_CONTEXT
            if context:
                sys_inst += f"\n🧭 Contexto de pantalla: {context.get('section')} ({context.get('route')})"

            res = await call_gemini_chat_with_tools(
                system_instruction=sys_inst,
                user_message=message,
                tools=TOOLS
            )

            if res.get("type") == "tool_call" and res.get("name") == "create_template":
                args = res.get("args", {})
                r = _crear_plantilla(db, _suscriptor_id(token_data, db), args)
                return {
                    "answer": (
                        f"Voy a crear la plantilla «{args.get('nombre', '')}»…\n"
                        f"¡Listo! Plantilla «{r['plantilla'].nombre}» creada con éxito."
                    ),
                    "action_log": r["action_log"],
                }

            return {"answer": res.get("text", "").strip(), "action_log": []}
        except Exception as e:
            print(f"Error llamando a Gemini en chat_service: {e}")

    openai_key = os.getenv("OPENAI_API_KEY")
    if not openai_key or not openai_key.strip():
        return {
            "answer": "El asistente virtual requiere que configure la clave GEMINI_API_KEY u OPENAI_API_KEY en las variables de entorno de Render.",
            "action_log": []
        }

    base_msgs = _build_msgs(message, context)
    msgs = (history or [])[-6:] + base_msgs  

    client = get_openai_client()
    resp = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=msgs,
        tools=TOOLS,
        tool_choice="auto",
        temperature=0.3,
    ).choices[0]

    # ——— Function-call ———
    if resp.finish_reason == "tool_calls":
        call = resp.message.tool_calls[0]
        if call.function.name == "create_template":
            args = json.loads(call.function.arguments)  # arguments llega como string
            r = _crear_plantilla(db, _suscriptor_id(token_data, db), args)
            return {
                "answer": (
                    f"Voy a crear la plantilla «{args['nombre']}»…\n"
                    f"¡Listo! Plantilla «{r['plantilla'].nombre}» creada con éxito."
                ),
                "action_log": r["action_log"],
            }

    # ——— Respuesta normal ———
    return {"answer": resp.message.content.strip(), "action_log": []}
