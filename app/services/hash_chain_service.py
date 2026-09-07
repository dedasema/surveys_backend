# app/services/hash_chain_service.py
import json
import hashlib
from typing import Dict, Any, List, Optional
from uuid import UUID
from sqlalchemy.orm import Session
from app.models.survey import RespuestaEncuesta, EntregaEncuesta

GENESIS_HASH = "0" * 64

def normalizar_contenido(payload: Any) -> str:
    """Normaliza cualquier estructura de datos en un string JSON determinístico y ordenado"""
    if isinstance(payload, str):
        try:
            parsed = json.loads(payload)
            return json.dumps(parsed, sort_keys=True, separators=(',', ':'), default=str)
        except Exception:
            return payload.strip()
    elif isinstance(payload, dict) or isinstance(payload, list):
        return json.dumps(payload, sort_keys=True, separators=(',', ':'), default=str)
    return str(payload)

def calcular_hash_respuesta(contenido: Any, hash_anterior: str = GENESIS_HASH) -> str:
    """
    Calcula determinísticamente el hash SHA-256 de una respuesta
    encadenada: SHA256(contenido_normalizado + hash_anterior).
    """
    contenido_norm = normalizar_contenido(contenido)
    cadena_a_hashear = f"{contenido_norm}|{hash_anterior or GENESIS_HASH}"
    return hashlib.sha256(cadena_a_hashear.encode("utf-8")).hexdigest()

def vincular_hash_cadena(
    db: Session,
    respuesta: RespuestaEncuesta,
    campana_id: Optional[UUID] = None
) -> str:
    """
    Asigna hash_anterior y calcula el nuevo hash de la respuesta
    vinculándola criptográficamente a la última respuesta previa.
    """
    query = (
        db.query(RespuestaEncuesta)
        .join(EntregaEncuesta, RespuestaEncuesta.entrega_id == EntregaEncuesta.id)
    )
    if campana_id:
        query = query.filter(EntregaEncuesta.campana_id == campana_id)

    if respuesta.id:
        query = query.filter(RespuestaEncuesta.id != respuesta.id)

    ultima_respuesta = (
        query.order_by(RespuestaEncuesta.recibido_en.desc())
        .first()
    )

    hash_anterior = ultima_respuesta.hash if (ultima_respuesta and ultima_respuesta.hash) else GENESIS_HASH
    nuevo_hash = calcular_hash_respuesta(respuesta.raw_payload or {}, hash_anterior)

    respuesta.hash_anterior = hash_anterior
    respuesta.hash = nuevo_hash
    return nuevo_hash

def verificar_integridad_cadena(
    db: Session,
    campana_id: Optional[UUID] = None
) -> Dict[str, Any]:
    """
    Recorre cronológicamente la cadena de respuestas verificando:
    1. Que el contenido no haya sido alterado (recalcula el hash).
    2. Que la cadena de punteros al hash anterior no esté rota.
    """
    query = (
        db.query(RespuestaEncuesta)
        .join(EntregaEncuesta, RespuestaEncuesta.entrega_id == EntregaEncuesta.id)
    )
    if campana_id:
        query = query.filter(EntregaEncuesta.campana_id == campana_id)

    respuestas: List[RespuestaEncuesta] = (
        query.order_by(RespuestaEncuesta.recibido_en.asc())
        .all()
    )

    if not respuestas:
        return {
            "campana_id": str(campana_id) if campana_id else "global",
            "total_respuestas": 0,
            "integro": True,
            "mensaje": "No hay respuestas registradas para verificar",
            "errores": []
        }

    errores = []
    hash_previo_esperado = GENESIS_HASH

    for idx, resp in enumerate(respuestas):
        # 1. Verificar apuntador anterior
        hash_anterior_actual = resp.hash_anterior or GENESIS_HASH
        if idx > 0 and hash_anterior_actual != hash_previo_esperado:
            errores.append({
                "posicion": idx,
                "respuesta_id": str(resp.id),
                "tipo_error": "ROTURA_DE_CADENA",
                "detalle": f"El hash anterior ({hash_anterior_actual[:12]}...) no coincide con el hash de la respuesta previa ({hash_previo_esperado[:12]}...)"
            })

        # 2. Verificar integridad del contenido recalculando el hash
        hash_recalculado = calcular_hash_respuesta(resp.raw_payload or {}, hash_anterior_actual)
        if resp.hash != hash_recalculado:
            errores.append({
                "posicion": idx,
                "respuesta_id": str(resp.id),
                "tipo_error": "CONTENIDO_MANIPULADO",
                "detalle": f"El hash registrado ({resp.hash[:12] if resp.hash else 'None'}...) no coincide con el contenido recalculado ({hash_recalculado[:12]}...)"
            })

        hash_previo_esperado = resp.hash or hash_recalculado

    es_integro = len(errores) == 0
    try:
        from app.services.quota_service import quota_tracker
        quota_tracker.registrar_verificacion_integridad(integro=es_integro, total_alteraciones=len(errores))
    except Exception:
        pass

    return {
        "campana_id": str(campana_id) if campana_id else "global",
        "total_respuestas": len(respuestas),
        "integro": es_integro,
        "ultimo_hash": respuestas[-1].hash if respuestas else None,
        "errores": errores
    }
