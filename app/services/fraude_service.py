# app/services/fraude_service.py
import re
import logging
from typing import Optional, List, Dict, Any
from uuid import UUID
from sqlalchemy.orm import Session

from app.models.survey import (
    RespuestaEncuesta, RespuestaPregunta, EntregaEncuesta, CampanaEncuesta
)
from app.models.fraude_flag import FraudeFlag
from app.services.embedding_service import generar_embedding, similitud_coseno
from app.services.gemini_service import call_gemini_text

logger = logging.getLogger(__name__)

def es_texto_gibberish_o_spam(texto: str) -> tuple[bool, float, str]:
    """
    Detecta patrones evidentes de spam, tecleo aleatorio o sinsentido.
    Retorna (es_fraude, confianza, justificacion).
    """
    t = texto.strip().lower()
    if len(t) < 3:
        return False, 0.0, ""

    # 1. Repetición extrema de un mismo caracter (ej: "aaaaaaa", "1111111")
    if re.search(r'(.)\1{5,}', t):
        return True, 0.95, "Patrón de caracteres idénticos repetidos consecutivamente."

    # 2. Secuencias típicas de tecleo rápido aleatorio (keyboard mash)
    keyboard_patterns = [
        "asdf", "qwert", "zxcv", "12345", "lkjh", "poiu", "mnbv"
    ]
    if any(p in t for p in keyboard_patterns) and len(t) < 30 and not any(palabra in t for palabra in ["bien", "mal", "servicio", "gracias", "atencion", "producto"]):
        return True, 0.90, "Patrón de tecleo aleatorio o teclado mashing detectado."

    # 3. Muy pocas vocales o consonantes consecutivas excesivas
    letras = [c for c in t if c.isalpha()]
    if len(letras) > 10:
        vocales = [c for c in letras if c in "aeiouáéíóú"]
        ratio_vocales = len(vocales) / len(letras)
        if ratio_vocales < 0.15 or ratio_vocales > 0.85:
            return True, 0.85, "Proporción anormal de vocales/consonantes (texto incoherente)."

    return False, 0.0, ""

async def evaluar_respuesta_antifraude(
    db: Session,
    respuesta_id: UUID,
    canal: str = "web"
) -> Optional[FraudeFlag]:
    """
    Evalúa integralmente una respuesta para detectar posible fraude o anomalía (RF21):
    1. Reglas determinísticas de spam / caracteres.
    2. Similitud semántica extrema (>= 0.95) con respuestas previas de la misma campaña.
    3. Clasificación de coherencia con IA.
    """
    respuesta = db.query(RespuestaEncuesta).filter_by(id=respuesta_id).first()
    if not respuesta:
        return None

    entrega = db.query(EntregaEncuesta).filter_by(id=respuesta.entrega_id).first()
    if not entrega:
        return None

    campana_id = entrega.campana_id

    # Obtener el contenido textual principal de la respuesta
    rps = db.query(RespuestaPregunta).filter_by(respuesta_id=respuesta.id).all()
    textos = [rp.texto.strip() for rp in rps if rp.texto and len(rp.texto.strip()) > 3]
    contenido_principal = " ".join(textos) if textos else ""

    if not contenido_principal:
        return None

    # 1. Señal por Regla: Gibberish o Spam directo
    es_spam, conf_spam, just_spam = es_texto_gibberish_o_spam(contenido_principal)
    if es_spam:
        flag = FraudeFlag(
            respuesta_id=respuesta.id,
            campana_id=campana_id,
            canal=canal,
            tipo_senal="regla",
            confianza=conf_spam,
            contenido_respuesta=contenido_principal,
            justificacion=just_spam,
            estado="pendiente"
        )
        db.add(flag)
        db.commit()
        db.refresh(flag)
        return flag

    # 2. Señal por Similitud Semántica (pgvector / embeddings)
    # Comparar con respuestas previas de la misma campaña
    respuestas_previas = (
        db.query(RespuestaPregunta)
        .join(RespuestaEncuesta, RespuestaPregunta.respuesta_id == RespuestaEncuesta.id)
        .join(EntregaEncuesta, RespuestaEncuesta.entrega_id == EntregaEncuesta.id)
        .filter(
            EntregaEncuesta.campana_id == campana_id,
            RespuestaEncuesta.id != respuesta.id,
            RespuestaPregunta.texto.isnot(None),
            RespuestaPregunta.texto != ""
        )
        .limit(50)
        .all()
    )

    if respuestas_previas:
        embedding_actual = await generar_embedding(contenido_principal)

        for previa in respuestas_previas:
            texto_previo = (previa.texto or "").strip()
            if not texto_previo or len(texto_previo) < 10:
                continue

            # Si es idéntico texto
            if contenido_principal.lower() == texto_previo.lower():
                flag = FraudeFlag(
                    respuesta_id=respuesta.id,
                    campana_id=campana_id,
                    canal=canal,
                    tipo_senal="regla",
                    confianza=0.99,
                    contenido_respuesta=contenido_principal,
                    respuesta_similar=texto_previo,
                    similitud_score=1.0,
                    justificacion="Texto idéntico duplicado detectado en la misma campaña.",
                    estado="pendiente"
                )
                db.add(flag)
                db.commit()
                db.refresh(flag)
                return flag

            # Similitud coseno por embedding
            embedding_previo = previa.embedding
            if embedding_previo is None or len(embedding_previo) != 768:
                embedding_previo = await generar_embedding(texto_previo)

            sim = similitud_coseno(embedding_actual, embedding_previo)
            if sim >= 0.95:
                flag = FraudeFlag(
                    respuesta_id=respuesta.id,
                    campana_id=campana_id,
                    canal=canal,
                    tipo_senal="similitud",
                    confianza=round(sim, 2),
                    contenido_respuesta=contenido_principal,
                    respuesta_similar=texto_previo,
                    similitud_score=round(sim, 2),
                    justificacion=f"Similitud coseno en embeddings de {sim:.2f} supera el umbral de 0.95 con respuesta previa.",
                    estado="pendiente"
                )
                db.add(flag)
                db.commit()
                db.refresh(flag)
                return flag

    return None
