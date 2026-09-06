# app/services/clustering_service.py
import json
import logging
from typing import List, Dict, Any
from uuid import UUID
from sqlalchemy.orm import Session

from app.models.survey import (
    CampanaEncuesta, EntregaEncuesta, RespuestaEncuesta, RespuestaPregunta
)
from app.services.embedding_service import generar_embedding, similitud_coseno
from app.services.gemini_service import call_gemini_text

logger = logging.getLogger(__name__)

async def agrupar_respuestas_en_clusters(
    db: Session,
    campana_id: UUID
) -> List[Dict[str, Any]]:
    """
    Agrupa semánticamente las respuestas abiertas de una campaña en clusters temáticos (RF22).
    Genera embeddings en pgvector para las respuestas que no lo tengan y utiliza Gemini
    para etiquetar y sintetizar cada grupo de temas emergentes.
    """
    # 1. Obtener todas las respuestas abiertas de la campaña
    items = (
        db.query(RespuestaPregunta)
        .join(RespuestaEncuesta, RespuestaPregunta.respuesta_id == RespuestaEncuesta.id)
        .join(EntregaEncuesta, RespuestaEncuesta.entrega_id == EntregaEncuesta.id)
        .filter(
            EntregaEncuesta.campana_id == campana_id,
            RespuestaPregunta.texto.isnot(None),
            RespuestaPregunta.texto != ""
        )
        .all()
    )

    textos = [i.texto.strip() for i in items if i.texto and len(i.texto.strip()) > 3]

    if not textos:
        return []

    # 2. Asegurar embeddings para cada respuesta
    vectores: List[List[float]] = []
    for item in items:
        texto = (item.texto or "").strip()
        if len(texto) <= 3:
            continue
        # Si ya tiene embedding en la columna
        vec = item.embedding if (item.embedding is not None and len(item.embedding) == 768) else None
        if vec is None:
            try:
                vec = await generar_embedding(texto)
                # Guardar en BD si es posible
                item.embedding = vec
            except Exception as e:
                logger.warning("No se pudo persistir embedding en BD: %s", e)
                vec = [0.0] * 768
        vectores.append(vec)

    db.commit()

    total_respuestas = len(textos)

    # 3. Agrupación por proximidad semántica (Umbral coseno ~ 0.70)
    # Algoritmo de clustering aglomerativo greedy ligero
    clusters_indices: List[List[int]] = []
    asignados = [False] * total_respuestas

    for i in range(total_respuestas):
        if asignados[i]:
            continue
        cluster_actual = [i]
        asignados[i] = True
        v_i = vectores[i]

        for j in range(i + 1, total_respuestas):
            if not asignados[j]:
                sim = similitud_coseno(v_i, vectores[j])
                if sim >= 0.70:
                    cluster_actual.append(j)
                    asignados[j] = True

        clusters_indices.append(cluster_actual)

    # Limitar a máximo 6 clusters principales ordenados por tamaño
    clusters_indices.sort(key=len, reverse=True)
    clusters_principales = clusters_indices[:6]

    # 4. Generar etiquetas y resúmenes con Gemini
    resultado_clusters: List[Dict[str, Any]] = []

    for idx, cluster in enumerate(clusters_principales, start=1):
        ejemplos = [textos[i] for i in cluster[:5]]
        conteo = len(cluster)
        proporcion = round((conteo / total_respuestas) * 100.0, 1)

        etiqueta, resumen = await _etiquetar_cluster_con_gemini(ejemplos)

        resultado_clusters.append({
            "id": f"cluster-{idx}",
            "etiqueta_ia": etiqueta,
            "resumen_ia": resumen,
            "total_respuestas": conteo,
            "proporcion": proporcion,
            "ejemplos_respuestas": ejemplos
        })

    return resultado_clusters

async def _etiquetar_cluster_con_gemini(ejemplos: List[str]) -> tuple[str, str]:
    """Genera una etiqueta descriptiva y un resumen para un grupo de respuestas afines"""
    ejemplos_str = "\n".join([f"- {e}" for e in ejemplos])
    prompt = f"""
Eres un analista experto de feedback y encuestas de satisfacción.
A continuación tienes un grupo de respuestas de usuarios que comparten un tema semántico común:

{ejemplos_str}

Instrucciones:
1. Asigna un título conciso para este tema ('etiqueta_ia', máximo 5-7 palabras).
2. Escribe una síntesis explicativa ('resumen_ia', 1 a 2 oraciones) de lo que expresan estos usuarios.
Devuelve ÚNICAMENTE un objeto JSON con este formato:
{{
  "etiqueta_ia": "Título del Tema",
  "resumen_ia": "Explicación concisa del sentir común expresado."
}}
"""
    try:
        raw_res = await call_gemini_text(prompt=prompt)
        clean = raw_res.strip()
        if "```json" in clean:
            clean = clean.split("```json")[1].split("```")[0].strip()
        elif "```" in clean:
            clean = clean.split("```")[1].split("```")[0].strip()
        data = json.loads(clean)
        return data.get("etiqueta_ia", "Tema General"), data.get("resumen_ia", "Comentarios y observaciones generales.")
    except Exception as e:
        logger.warning("Fallback en etiquetado de cluster: %s", e)
        # Fallback inteligente
        primer_ejemplo = ejemplos[0] if ejemplos else "Feedback general"
        etiqueta = primer_ejemplo[:40] + ("..." if len(primer_ejemplo) > 40 else "")
        return etiqueta, "Respuestas agrupadas por coincidencia semántica."
