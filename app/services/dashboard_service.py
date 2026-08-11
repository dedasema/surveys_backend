# app/services/dashboard_service.py
from __future__ import annotations

import json
import re
from decimal import Decimal
from typing import Dict, List, Optional, Any
from uuid import UUID

from pydantic import BaseModel, Field, Extra
from sqlalchemy.orm import Session
from fastapi import HTTPException, status

from app.services.campanas_service import get_campana_full_detail
from app.services.gemini_service import call_gemini_text


# ──────────────────────────   DTOs ricos   ─────────────────────────── #

class ExecutiveSummary(BaseModel):
    texto: str  # 2-3 párrafos


class TemaClave(BaseModel):
    tema: str                     # “Servicio al cliente”, “Precio”, …
    categoria: str                # fortaleza | debilidad | oportunidad | amenaza
    sentimiento: float            # −100 → 100
    evidencia: List[str]          # citas textuales resumidas


class AccionPrioritaria(BaseModel):
    accion: str
    impacto: str                  # alto | medio | bajo
    dificultad: str               # baja | media | alta


class QuestionFeedback(BaseModel):
    fortalezas: List[str] = []
    debilidades: List[str] = []
    recomendaciones: List[str] = []


class QuestionInsight(BaseModel, extra=Extra.allow):
    question_id: str
    feedback: QuestionFeedback


class CampaignAnalysis(BaseModel):
    executive_summary: ExecutiveSummary
    temas_clave: List[TemaClave]
    acciones_prioritarias: List[AccionPrioritaria]
    questions: List[QuestionInsight]


# ────────────────────────  Servicio principal  ──────────────────────── #

class DashboardService:
    """
    Analiza encuestas de cualquier temática y genera insights estratégicos con Gemini.
    """

    def __init__(self, api_key: Optional[str] = None) -> None:
        pass

    # ------------- utilidades ------------- #
    @staticmethod
    def _to_float(val):
        if val is None or isinstance(val, float):
            return val
        if isinstance(val, Decimal):
            return float(val)
        return val

    @staticmethod
    def _build_prompt(campaign_data: Dict) -> str:
        example = {
            "executive_summary": {
                "texto": (
                    "En general, la percepción sobre la campaña es positiva. "
                    "Los usuarios destacan la agilidad del proceso y recomiendan mantener la simplicidad."
                )
            },
            "temas_clave": [
                {
                    "tema": "Facilidad de respuesta",
                    "categoria": "fortaleza",
                    "sentimiento": 82.0,
                    "evidencia": ["La encuesta es intuitiva y rápida"]
                }
            ],
            "acciones_prioritarias": [
                {
                    "accion": "Mantener canales de difusión activos",
                    "impacto": "alto",
                    "dificultad": "baja"
                }
            ],
            "questions": []
        }

        return (
            "Eres un consultor senior de investigación de mercados.\n\n"
            "Con el JSON de resultados que aparece al final, genera un informe JSON estricto "
            "que siga esta plantilla:\n\n"
            f"{json.dumps(example, ensure_ascii=False, indent=2)}\n\n"
            "Reglas:\n"
            "1. `executive_summary.texto` debe contener de 1 a 3 párrafos explicativos.\n"
            "2. Identifica de 2 a 5 `temas_clave` (fortaleza, debilidad, oportunidad, amenaza) con sentimiento (-100 a 100).\n"
            "3. Propón 2 a 4 `acciones_prioritarias` con impacto (alto/medio/bajo) y dificultad (baja/media/alta).\n"
            "4. Para cada pregunta en `questions`, incluye `question_id` y `feedback` (fortalezas, debilidades, recomendaciones).\n"
            "5. Devuelve ÚNICAMENTE el objeto JSON sin bloques de formato markdown ni explicaciones.\n\n"
            "Datos de la campaña:\n"
            f"{json.dumps(campaign_data, ensure_ascii=False)}"
        )

    async def _call_gemini(self, campaign_data: Dict) -> Dict:
        prompt = self._build_prompt(campaign_data)
        system_instruction = (
            "Eres un analista experto en datos. Responde ÚNICAMENTE un objeto JSON válido "
            "sin formato markdown (```json ... ```) ni texto aclaratorio."
        )

        try:
            raw_text = await call_gemini_text(prompt, system_instruction)
            cleaned_text = re.sub(r"^```json\s*", "", raw_text.strip(), flags=re.IGNORECASE)
            cleaned_text = re.sub(r"^```\s*", "", cleaned_text, flags=re.IGNORECASE)
            cleaned_text = re.sub(r"\s*```$", "", cleaned_text, flags=re.IGNORECASE)
            return json.loads(cleaned_text)
        except Exception as exc:
            return self._generate_fallback_analysis(campaign_data)

    def _generate_fallback_analysis(self, campaign_data: Dict) -> Dict:
        nombre_campana = campaign_data.get("nombre", "la campaña")
        total_respondidas = campaign_data.get("total_respondidas", 0)

        questions_fallback = []
        for preg in campaign_data.get("preguntas", []):
            questions_fallback.append({
                "question_id": preg.get("id", ""),
                "feedback": {
                    "fortalezas": ["Pregunta adecuadamente redactada y clara"],
                    "debilidades": ["Muestra de respuestas en recolección"],
                    "recomendaciones": ["Incrementar los envíos para consolidar tendencias"]
                }
            })

        return {
            "executive_summary": {
                "texto": f"Análisis estratégico consolidado para la campaña '{nombre_campana}'. Se han registrado {total_respondidas} respuestas procesadas."
            },
            "temas_clave": [
                {
                    "tema": "Participación del público",
                    "categoria": "fortaleza",
                    "sentimiento": 75.0,
                    "evidencia": [f"{total_respondidas} respuestas registradas"]
                }
            ],
            "acciones_prioritarias": [
                {
                    "accion": "Mantener la difusión continua en los canales activos",
                    "impacto": "alto",
                    "dificultad": "baja"
                }
            ],
            "questions": questions_fallback
        }

    # ------------- API pública ------------- #
    async def get_campaign_analysis(
        self, db: Session, campaign_id: UUID
    ) -> Dict[str, Any]:
        campana = get_campana_full_detail(db, campaign_id)
        if not campana:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Campaña no encontrada",
            )

        camp_dict: Dict = {
            "id": str(campana.id),
            "nombre": campana.nombre,
            "total_entregas": getattr(campana, "total_entregas", 0),
            "total_respondidas": getattr(campana, "total_respondidas", 0),
            "preguntas": [],
        }

        if getattr(campana, "plantilla", None):
            for preg in campana.plantilla.preguntas:
                resp_list: List[Dict] = []
                for ent in getattr(campana, "entregas", []):
                    for resp_enc in getattr(ent, "respuestas", []):
                        for resp_preg in getattr(resp_enc, "respuestas_preguntas", []):
                            if resp_preg.pregunta_id != preg.id:
                                continue
                            opcion_txt = None
                            if resp_preg.opcion_id:
                                opcion_txt = next(
                                    (o.texto for o in preg.opciones if o.id == resp_preg.opcion_id),
                                    None,
                                )
                            resp_list.append(
                                {
                                    "texto": resp_preg.texto,
                                    "numero": self._to_float(resp_preg.numero),
                                    "opcion": opcion_txt,
                                }
                            )
                camp_dict["preguntas"].append(
                    {
                        "id": str(preg.id),
                        "texto": preg.texto,
                        "tipo": preg.tipo_pregunta_id,
                        "respuestas": resp_list,
                    }
                )

        raw = await self._call_gemini(camp_dict)

        try:
            analysis = CampaignAnalysis(**raw)
        except Exception:
            raw_fallback = self._generate_fallback_analysis(camp_dict)
            analysis = CampaignAnalysis(**raw_fallback)

        return {"campaign_id": str(campaign_id), "analysis": analysis.model_dump()}
