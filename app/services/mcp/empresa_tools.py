# app/services/mcp/empresa_tools.py
from typing import Dict, Any, Optional
from uuid import UUID
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models.suscriptor import Suscriptor
from app.models.subscription import PlanSuscripcion, SuscripcionSuscriptor
from app.models.survey import (
    CampanaEncuesta, PlantillaEncuesta, EntregaEncuesta, RespuestaEncuesta, RespuestaPregunta
)
from app.models.cuenta_usuario import CuentaUsuario
from app.models.fraude_flag import FraudeFlag
from app.models.agregado_campana import AgregadoCampana
from .registry import mcp_registry
from .context import ActorContext

@mcp_registry.register(
    name="obtener_resumen_empresa",
    description="Obtiene un resumen ejecutivo de la empresa suscriptora: nombre, plan activo, total de plantillas, campañas activas, respuestas totales recolectadas y operadores vinculados.",
    input_schema={
        "type": "object",
        "properties": {},
        "required": []
    },
    roles_permitidos=["empresa", "suscriptor", "admin"]
)
async def obtener_resumen_empresa_handler(db: Session, actor: ActorContext, args: Dict[str, Any]) -> Dict[str, Any]:
    suscriptor_id = actor.requiere_suscriptor_id()

    suscriptor = db.query(Suscriptor).filter_by(id=suscriptor_id).first()
    if not suscriptor:
        return {"error": "Empresa no encontrada"}

    # Obtener suscripción y plan activo
    suscripcion = (
        db.query(SuscripcionSuscriptor)
        .filter(SuscripcionSuscriptor.suscriptor_id == suscriptor_id)
        .order_by(SuscripcionSuscriptor.inicia_en.desc())
        .first()
    )
    plan_nombre = "Gratuito (Por defecto)"
    if suscripcion and suscripcion.plan:
        plan_nombre = suscripcion.plan.nombre

    # Métricas cuantitativas
    total_plantillas = db.query(func.count(PlantillaEncuesta.id)).filter(PlantillaEncuesta.suscriptor_id == suscriptor_id).scalar() or 0
    total_campanas = db.query(func.count(CampanaEncuesta.id)).filter(CampanaEncuesta.suscriptor_id == suscriptor_id).scalar() or 0
    total_operadores = db.query(func.count(CuentaUsuario.id)).filter(CuentaUsuario.suscriptor_id == suscriptor_id).scalar() or 0

    # Total respuestas recolectadas en campañas de la empresa
    total_respuestas = (
        db.query(func.count(RespuestaEncuesta.id))
        .join(EntregaEncuesta, RespuestaEncuesta.entrega_id == EntregaEncuesta.id)
        .join(CampanaEncuesta, EntregaEncuesta.campana_id == CampanaEncuesta.id)
        .filter(CampanaEncuesta.suscriptor_id == suscriptor_id)
        .scalar() or 0
    )

    return {
        "empresa_nombre": suscriptor.nombre,
        "email": suscriptor.email,
        "plan_actual": plan_nombre,
        "total_plantillas": total_plantillas,
        "total_campanas": total_campanas,
        "total_respuestas": total_respuestas,
        "total_operadores": total_operadores
    }


@mcp_registry.register(
    name="listar_campanas_empresa",
    description="Lista las campañas de encuestas creadas por la empresa suscriptora, con filtros opcionales por estado (activa, borrador, finalizada).",
    input_schema={
        "type": "object",
        "properties": {
            "estado": {
                "type": "string",
                "description": "Filtro opcional por estado de campaña (ej: activa, borrador, finalizada)"
            },
            "limite": {
                "type": "integer",
                "description": "Cantidad máxima de campañas a listar (default: 10)"
            }
        },
        "required": []
    },
    roles_permitidos=["empresa", "suscriptor", "admin", "analista"]
)
async def listar_campanas_empresa_handler(db: Session, actor: ActorContext, args: Dict[str, Any]) -> Dict[str, Any]:
    suscriptor_id = actor.requiere_suscriptor_id()
    limite = min(int(args.get("limite", 10)), 50)

    query = db.query(CampanaEncuesta).filter(CampanaEncuesta.suscriptor_id == suscriptor_id)
    
    estado_filtro = args.get("estado")
    if estado_filtro:
        from app.models.catalogos import EstadoCampana
        estado_obj = db.query(EstadoCampana).filter_by(nombre=estado_filtro.lower()).first()
        if estado_obj:
            query = query.filter(CampanaEncuesta.estado_id == estado_obj.id)

    campanas = query.order_by(CampanaEncuesta.creado_en.desc()).limit(limite).all()

    items = []
    for c in campanas:
        total_entregas = db.query(func.count(EntregaEncuesta.id)).filter(EntregaEncuesta.campana_id == c.id).scalar() or 0
        total_respuestas = (
            db.query(func.count(RespuestaEncuesta.id))
            .join(EntregaEncuesta, RespuestaEncuesta.entrega_id == EntregaEncuesta.id)
            .filter(EntregaEncuesta.campana_id == c.id)
            .scalar() or 0
        )
        items.append({
            "id": str(c.id),
            "nombre": c.nombre,
            "canal_id": c.canal_id,
            "estado_id": c.estado_id,
            "creado_en": c.creado_en.isoformat() if c.creado_en else None,
            "total_entregas": total_entregas,
            "total_respuestas": total_respuestas
        })

    return {
        "total_encontradas": len(items),
        "campanas": items
    }


@mcp_registry.register(
    name="obtener_metricas_campana",
    description="Consulta las métricas detalladas y KPIs de una campaña específica de la empresa: total despachos, respuestas, tasa de completitud y promedios analíticos.",
    input_schema={
        "type": "object",
        "properties": {
            "campana_id": {
                "type": "string",
                "description": "UUID de la campaña a consultar"
            }
        },
        "required": ["campana_id"]
    },
    roles_permitidos=["empresa", "suscriptor", "admin", "analista"]
)
async def obtener_metricas_campana_handler(db: Session, actor: ActorContext, args: Dict[str, Any]) -> Dict[str, Any]:
    suscriptor_id = actor.requiere_suscriptor_id()
    campana_id_str = args.get("campana_id")
    if not campana_id_str:
        return {"error": "campana_id es requerido"}

    try:
        campana_uuid = UUID(campana_id_str)
    except ValueError:
        return {"error": "campana_id no tiene formato UUID válido"}

    # Garantizar aislamiento multi-tenant: la campaña debe pertenecer a este suscriptor
    campana = db.query(CampanaEncuesta).filter(
        CampanaEncuesta.id == campana_uuid,
        CampanaEncuesta.suscriptor_id == suscriptor_id
    ).first()

    if not campana:
        return {"error": "Campaña no encontrada o no pertenece a tu empresa"}

    total_entregas = db.query(func.count(EntregaEncuesta.id)).filter(EntregaEncuesta.campana_id == campana.id).scalar() or 0
    total_respuestas = (
        db.query(func.count(RespuestaEncuesta.id))
        .join(EntregaEncuesta, RespuestaEncuesta.entrega_id == EntregaEncuesta.id)
        .filter(EntregaEncuesta.campana_id == campana.id)
        .scalar() or 0
    )
    tasa_completitud = round((total_respuestas / total_entregas * 100.0), 2) if total_entregas > 0 else 0.0

    # Consultar si existen agregados analíticos
    agregados = (
        db.query(AgregadoCampana)
        .filter(AgregadoCampana.campana_id == campana.id)
        .order_by(AgregadoCampana.orden_periodo.asc())
        .all()
    )
    agregados_info = [
        {
            "periodo": a.periodo,
            "total_respuestas": a.total_respuestas,
            "promedio_satisfaccion": a.promedio_satisfaccion,
            "tasa_completitud": a.tasa_completitud
        }
        for a in agregados
    ]

    return {
        "campana_id": str(campana.id),
        "nombre": campana.nombre,
        "total_entregas": total_entregas,
        "total_respuestas": total_respuestas,
        "tasa_completitud_porcentaje": tasa_completitud,
        "agregados_historicos": agregados_info
    }


@mcp_registry.register(
    name="consultar_alertas_fraude",
    description="Consulta las alertas de fraude y anomalías detectadas en las encuestas de la empresa (respuestas sospechosas, duplicidad, incoherencia semántica).",
    input_schema={
        "type": "object",
        "properties": {
            "limite": {
                "type": "integer",
                "description": "Cantidad máxima de alertas a retornar (default: 10)"
            },
            "estado": {
                "type": "string",
                "description": "Filtro opcional: 'pendiente', 'confirmado_fraude', 'descartado_valido'"
            }
        },
        "required": []
    },
    roles_permitidos=["empresa", "suscriptor", "admin", "analista"]
)
async def consultar_alertas_fraude_handler(db: Session, actor: ActorContext, args: Dict[str, Any]) -> Dict[str, Any]:
    suscriptor_id = actor.requiere_suscriptor_id()
    limite = min(int(args.get("limite", 10)), 50)
    estado = args.get("estado")

    query = (
        db.query(FraudeFlag)
        .join(CampanaEncuesta, FraudeFlag.campana_id == CampanaEncuesta.id)
        .filter(CampanaEncuesta.suscriptor_id == suscriptor_id)
    )

    if estado:
        query = query.filter(FraudeFlag.estado == estado)

    alertas = query.order_by(FraudeFlag.creado_en.desc()).limit(limite).all()

    items = []
    for a in alertas:
        items.append({
            "id": str(a.id),
            "campana_id": str(a.campana_id),
            "canal": a.canal,
            "tipo_senal": a.tipo_senal,
            "confianza": a.confianza,
            "estado": a.estado,
            "justificacion": a.justificacion,
            "creado_en": a.creado_en.isoformat() if a.creado_en else None
        })

    return {
        "total_alertas": len(items),
        "alertas": items
    }


@mcp_registry.register(
    name="sugerir_preguntas_encuesta",
    description="Genera sugerencias de preguntas estructuradas y tipos de pregunta recomendados (NPS, escala Likert, opción múltiple, abierta) para un objetivo de encuesta dado.",
    input_schema={
        "type": "object",
        "properties": {
            "objetivo": {
                "type": "string",
                "description": "Objetivo o tema de la encuesta (ej: satisfacción de cliente, clima laboral, evaluación de evento)"
            },
            "canal": {
                "type": "string",
                "description": "Canal sugerido: 'web', 'whatsapp', 'voz' o 'papel' (default: 'web')"
            }
        },
        "required": ["objetivo"]
    },
    roles_permitidos=["empresa", "suscriptor", "admin", "analista", "operator"]
)
async def sugerir_preguntas_encuesta_handler(db: Session, actor: ActorContext, args: Dict[str, Any]) -> Dict[str, Any]:
    objetivo = str(args.get("objetivo", "")).strip()
    canal = str(args.get("canal", "web")).strip().lower()

    if not objetivo:
        return {"error": "El campo 'objetivo' es obligatorio"}

    # Banco de plantillas recomendadas según el dominio
    sugerencias = [
        {
            "orden": 1,
            "texto": f"Del 0 al 10, ¿con qué probabilidad recomendarías nuestros servicios considerando {objetivo}?",
            "tipo": "nps",
            "obligatoria": True
        },
        {
            "orden": 2,
            "texto": "¿Cuál es tu nivel de satisfacción general con la experiencia recibida?",
            "tipo": "escala",
            "opciones": ["Muy insatisfecho", "Insatisfecho", "Neutral", "Satisfecho", "Muy satisfecho"],
            "obligatoria": True
        },
        {
            "orden": 3,
            "texto": "¿Qué aspecto considerás que podríamos mejorar principalmente?",
            "tipo": "opcion_multiple" if canal != "voz" else "texto",
            "opciones": ["Tiempo de respuesta", "Atención del personal", "Calidad del servicio", "Precios / Costos", "Otro"],
            "obligatoria": False
        },
        {
            "orden": 4,
            "texto": "¿Tenés algún comentario adicional o sugerencia que quieras compartirnos?",
            "tipo": "texto",
            "obligatoria": False
        }
    ]

    return {
        "objetivo": objetivo,
        "canal_recomendado": canal,
        "total_preguntas_sugeridas": len(sugerencias),
        "preguntas": sugerencias
    }


@mcp_registry.register(
    name="consultar_conocimiento_rag",
    description="Busca semánticamente en las respuestas cualitativas de encuestas recolectadas (texto, transcripciones de audio y OCR de papel) usando pgvector, devolviendo fragmentos relevantes y evidencia verificada.",
    input_schema={
        "type": "object",
        "properties": {
            "pregunta": {
                "type": "string",
                "description": "Consulta o pregunta analítica a buscar en el feedback cualitativo de las encuestas"
            },
            "campana_id": {
                "type": "string",
                "description": "UUID opcional de campaña para acotar la búsqueda semántica"
            },
            "top_k": {
                "type": "integer",
                "description": "Cantidad de citas relevantes a recuperar (default: 4)"
            }
        },
        "required": ["pregunta"]
    },
    roles_permitidos=["empresa", "suscriptor", "admin", "analista"]
)
async def consultar_conocimiento_rag_handler(db: Session, actor: ActorContext, args: Dict[str, Any]) -> Dict[str, Any]:
    suscriptor_id = actor.requiere_suscriptor_id()
    pregunta = str(args.get("pregunta", "")).strip()
    if not pregunta:
        return {"error": "El parámetro 'pregunta' es obligatorio"}

    campana_id_str = args.get("campana_id")
    campana_uuid = None
    if campana_id_str:
        try:
            campana_uuid = UUID(campana_id_str)
            camp = db.query(CampanaEncuesta).filter_by(id=campana_uuid, suscriptor_id=suscriptor_id).first()
            if not camp:
                return {"error": "Campaña no encontrada o no pertenece a tu empresa"}
        except ValueError:
            return {"error": "campana_id no tiene formato UUID válido"}

    top_k = min(int(args.get("top_k", 4)), 10)

    # 1. Obtener respuestas candidatas de la BD filtradas estrictamente por suscriptor_id
    query = (
        db.query(RespuestaPregunta)
        .join(RespuestaEncuesta, RespuestaPregunta.respuesta_id == RespuestaEncuesta.id)
        .join(EntregaEncuesta, RespuestaEncuesta.entrega_id == EntregaEncuesta.id)
        .join(CampanaEncuesta, EntregaEncuesta.campana_id == CampanaEncuesta.id)
        .filter(
            CampanaEncuesta.suscriptor_id == suscriptor_id,
            RespuestaPregunta.texto.isnot(None),
            RespuestaPregunta.texto != ""
        )
    )
    if campana_uuid:
        query = query.filter(EntregaEncuesta.campana_id == campana_uuid)

    items = query.order_by(RespuestaEncuesta.recibido_en.desc()).limit(50).all()

    if not items:
        return {
            "pregunta": pregunta,
            "total_citas": 0,
            "fuentes_citadas": [],
            "mensaje": "No se encontraron respuestas registradas aún para analizar."
        }

    from app.services.embedding_service import generar_embedding, similitud_coseno
    emb_pregunta = await generar_embedding(pregunta)

    candidatos = []
    for item in items:
        t = (item.texto or "").strip()
        if len(t) < 4:
            continue
        vec = item.embedding
        if vec is None or len(vec) != 768:
            vec = await generar_embedding(t)
            try:
                item.embedding = vec
            except Exception:
                pass
        sim = similitud_coseno(emb_pregunta, vec)
        candidatos.append((sim, item))

    candidatos.sort(key=lambda x: x[0], reverse=True)
    top_candidatos = candidatos[:top_k]

    fuentes_citadas = []
    for sim, rp in top_candidatos:
        resp = rp.respuesta
        entrega = resp.entrega if resp else None
        camp = entrega.campana if entrega else None

        canal_nombre = "web"
        if entrega and entrega.canal_id == 1:
            canal_nombre = "email"
        elif entrega and entrega.canal_id == 2:
            canal_nombre = "voz"
        elif entrega and entrega.canal_id == 3:
            canal_nombre = "ocr"
        elif entrega and entrega.canal_id == 4:
            canal_nombre = "whatsapp"

        fecha_str = resp.recibido_en.strftime("%Y-%m-%d") if (resp and resp.recibido_en) else "Reciente"
        camp_nombre = camp.nombre if camp else "Campaña"

        fuentes_citadas.append({
            "id": str(rp.id),
            "canal": canal_nombre,
            "campana": camp_nombre,
            "fragmento": rp.texto[:300],
            "similitud_score": round(max(0.1, sim), 2),
            "fecha": fecha_str
        })

    return {
        "pregunta": pregunta,
        "total_citas": len(fuentes_citadas),
        "fuentes_citadas": fuentes_citadas
    }

