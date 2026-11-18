# app/services/chat_landing_service.py
import os
import json
import logging
import httpx
from typing import List, Optional, Dict, Any

from app.core.config import settings
from app.schemas.chat_landing import ChatLandingOut, ActionItem, ChatMessageItem
from app.services.gemini_service import get_gemini_api_key, _execute_gemini_request, GEMINI_BASE_URL

logger = logging.getLogger(__name__)

SYSTEM_PROMPT_LANDING = """Eres el Asesor Virtual de Producto y Ventas de SurveySaaS.
Tu objetivo principal es responder dudas a visitantes de la Landing Page, explicar el valor de la plataforma y guiarlos amablemente hacia el registro o prueba de la solución.
DIRECTRICES DE PERSONALIDAD Y TONO:
- Tono: Profesional, cálido, claro y resolutivo. Habla en español neutro o rioplatense natural según el contexto.
- Enfoque: Comercial, educativo (pre-venta) y de onboarding.
- Sé conciso: Respuestas directas de 2 a 4 párrafos como máximo, utilizando viñetas cuando detalles opciones.
CONOCIMIENTO CLAVE DEL PRODUCTO:
1. ¿Qué es SurveySaaS?:
   Plataforma integral de encuestas multicanal potenciada por Inteligencia Artificial.
   Soporta recolección por:
   - Voz / Audio con IA: Entrevistas por llamadas telefónicas o audios web, con transcripción automática Whisper/Speech-to-Text y análisis de sentimiento.
   - Enlaces Web y QR: Formularios responsivos para WhatsApp, emails o redes sociales.
   - Papel con Escaneo OCR: Generación de formularios PDF imprimibles con QR de trazabilidad y digitalización automática de respuestas manuscritas con visión artificial.
   - Analítica Avanzada: Detección de fraude, clustering semántico de opiniones y reportes ejecutivos.
2. Planes y Precios Oficiales:
   - Plan Gratuito ($0.00 USD/mes): 3 plantillas de encuestas, 100 respuestas/mes, 1 operador de equipo, canales email y web, prueba de OCR e IA.
   - Plan Profesional ($29.99 USD/mes): 50 plantillas, 5.000 respuestas/mes, 5 operadores de equipo, OCR papel con IA, análisis de audio y voz con IA, reportes avanzados.
   - Plan Enterprise ($99.99 USD/mes): Plantillas, campañas, respuestas y operadores ILIMITADOS, OCR papel y asistente de voz, exportación completa, acceso a API y soporte prioritario con SLA.
3. Seguridad y Privacidad:
   - Cifrado TLS 1.3 en tránsito y AES-256 en reposo.
   - Aislamiento multi-tenant estricto (los datos de cada empresa están 100% segregados).
   - Cadena de custodia criptográfica en respuestas (hash-chaining) para evitar manipulaciones.
4. Llamados a la Acción (Call to Action):
   - Invita a crear una cuenta gratuita en: `/register`
   - Si ya tienen cuenta, indícales iniciar sesión en: `/login`
   - Si quieren comparar planes en la landing, refiérelos a la sección: `#precios`
LIMITACIONES ESTRICTAS DE SEGURIDAD:
- NO intentes consultar datos privados de clientes, encuestas o usuarios registrados.
- NO ejecutes herramientas o endpoints de mutación en la base de datos (tú eres un asesor público).
- Si te preguntan algo fuera de SurveySaaS, responde educadamente que tu especialidad es asesorar sobre las funciones, planes y tecnología de SurveySaaS.
"""

def _extract_actions(user_msg: str, answer: str) -> List[ActionItem]:
    """Genera botones de acción / CTAs relevantes a partir del contexto del diálogo."""
    text_combined = f"{user_msg} {answer}".lower()
    actions: List[ActionItem] = []

    # Registro / Crear cuenta
    if any(k in text_combined for k in ["/register", "registr", "crear cuenta", "cuenta gratis", "gratuito", "probar", "empezar"]):
        actions.append(ActionItem(label="Crear cuenta gratuita", href="/register"))

    # Precios / Planes
    if any(k in text_combined for k in ["#precios", "precio", "plan", "costo", "tarifa", "profesional", "enterprise", "cuánto cuesta"]):
        actions.append(ActionItem(label="Ver planes y precios", href="#precios"))

    # Login / Ingreso
    if any(k in text_combined for k in ["/login", "iniciar sesión", "ingresar", "ya tengo cuenta"]):
        actions.append(ActionItem(label="Iniciar sesión", href="/login"))

    # Fallback si no hubo coincidencia específica: siempre ofrecer ver precios y crear cuenta
    if not actions:
        actions = [
            ActionItem(label="Crear cuenta gratuita", href="/register"),
            ActionItem(label="Ver planes y precios", href="#precios"),
        ]

    # Eliminar duplicados por href
    seen = set()
    unique_actions = []
    for a in actions:
        if a.href not in seen:
            seen.add(a.href)
            unique_actions.append(a)

    return unique_actions

def _smart_fallback_response(message: str) -> str:
    """Respuesta comercial contextual en caso de indisponibilidad temporal de LLM."""
    msg_lower = message.lower()
    if any(k in msg_lower for k in ["precio", "plan", "costo", "cuanto", "cuánto", "tarifa"]):
        return (
            "¡Hola! En **SurveySaaS** disponemos de 3 planes adaptados a cada etapa de tu empresa:\n\n"
            "• **Plan Gratuito ($0.00 USD/mes)**: 3 plantillas, 100 respuestas al mes, 1 operador y acceso a canales web/email con prueba de OCR e IA.\n"
            "• **Plan Profesional ($29.99 USD/mes)**: 50 plantillas, 5.000 respuestas/mes, 5 operadores, análisis de audio/voz y OCR papel con IA.\n"
            "• **Plan Enterprise ($99.99 USD/mes)**: Plantillas, campañas, respuestas y operadores ilimitados, OCR papel, asistente de voz, API y SLA prioritario.\n\n"
            "Podés registrarte gratis ahora mismo en `/register` o comparar la tabla en la sección `#precios`."
        )
    elif any(k in msg_lower for k in ["voz", "audio", "llamada", "habla", "whisper"]):
        return (
            "En **SurveySaaS** revolucionamos la captura de datos integrando **Voz y Audio con IA**. "
            "Permitimos realizar encuestas telefónicas o por notas de voz web, transcribiendo automáticamente con Whisper "
            "y analizando el sentimiento y tono de las respuestas en tiempo real.\n\n"
            "¡Creá tu cuenta en `/register` para probarlo en el plan gratuito!"
        )
    elif any(k in msg_lower for k in ["papel", "ocr", "escan", "físico", "imprim"]):
        return (
            "Nuestra tecnología de **Papel con Escaneo OCR** te permite generar formularios PDF imprimibles con QR de trazabilidad única. "
            "Luego, con solo tomarles una foto o escanearlos, nuestra visión artificial digitaliza automáticamente las marcas y escritura a mano.\n\n"
            "Ideal para relevamientos de campo o zonas sin conectividad. Podés comenzar en `/register`."
        )
    elif any(k in msg_lower for k in ["seguridad", "cifrado", "datos", "privacidad"]):
        return (
            "La seguridad es nuestro pilar fundamental:\n\n"
            "• **Cifrado de nivel bancario**: TLS 1.3 en tránsito y AES-256 en reposo.\n"
            "• **Aislamiento Multi-Tenant**: Los datos de tu organización están 100% segregados.\n"
            "• **Hash-Chaining Criptográfico**: Cada respuesta cuenta con una cadena de custodia inmutable contra manipulaciones."
        )
    else:
        return (
            "¡Hola! Soy el asesor de **SurveySaaS**, la plataforma multicanal que potencia la recolección y análisis de encuestas "
            "mediante Inteligencia Artificial (Voz/Audio, Web/QR, WhatsApp y Papel con OCR).\n\n"
            "¿En qué te puedo asesorar hoy? Podés preguntarme por nuestras funciones de IA, los canales disponibles o explorar nuestros planes en `#precios`."
        )

async def _call_gemini_landing(message: str, history: Optional[List[ChatMessageItem]]) -> Optional[str]:
    api_key = get_gemini_api_key()
    if not api_key:
        return None

    contents: List[Dict[str, Any]] = []
    if history:
        for item in history[-8:]:
            role = "user" if item.sender == "user" else "model"
            contents.append({"role": role, "parts": [{"text": item.text}]})

    contents.append({"role": "user", "parts": [{"text": message}]})

    payload = {
        "contents": contents,
        "systemInstruction": {
            "parts": [{"text": SYSTEM_PROMPT_LANDING}]
        },
        "generationConfig": {
            "temperature": 0.4,
            "maxOutputTokens": 800
        }
    }

    try:
        async with httpx.AsyncClient(timeout=25.0) as client:
            res = await _execute_gemini_request(client, api_key, payload, tipo="landing_chat")
            if res and res.status_code == 200:
                data = res.json()
                candidates = data.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    if parts:
                        return parts[0].get("text", "").strip()
    except Exception as e:
        logger.warning(f"Error llamando a Gemini para chat landing: {e}")

    return None

async def chat_landing_completion(
    message: str,
    history: Optional[List[ChatMessageItem]] = None
) -> ChatLandingOut:
    """Procesa una consulta del chatbot público de la Landing Page usando Gemini con fallback contextual."""
    clean_msg = message.strip()
    if not clean_msg:
        return ChatLandingOut(
            answer="¡Hola! ¿En qué puedo ayudarte a conocer sobre SurveySaaS?",
            actions=[
                ActionItem(label="Crear cuenta gratuita", href="/register"),
                ActionItem(label="Ver planes y precios", href="#precios"),
            ]
        )

    # 1. Intentar con Gemini
    answer = await _call_gemini_landing(clean_msg, history)

    # 2. Si Gemini no está disponible o falla, usar fallback estructurado inteligente
    if not answer:
        answer = _smart_fallback_response(clean_msg)

    # Generar acciones interactivas recomendadas
    actions = _extract_actions(clean_msg, answer)

    return ChatLandingOut(answer=answer, actions=actions)
