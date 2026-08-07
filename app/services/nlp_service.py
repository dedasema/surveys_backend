# app/services/nlp_service.py
from __future__ import annotations
import os, uuid, json, re, functools, itertools
from datetime import datetime
from collections import Counter, defaultdict, OrderedDict
from typing import List, Dict, Any, Optional

try:
    import numpy as np
except Exception:
    np = None

try:
    import pandas as pd
except Exception:
    pd = None

from sqlalchemy.orm import Session
from fastapi import HTTPException
from openai import OpenAI

from app.models.survey import (
    CampanaEncuesta, EntregaEncuesta, RespuestaEncuesta,
    RespuestaPregunta, PreguntaEncuesta, OpcionEncuesta
)
from app.schemas.nlp_schema import NLPAnalysisRequest, NLPAnalysisResponse

# ─────────────────── Recursos globales Lazy ────────────────────
_client = None
_sentiment_es = None

def get_openai_client():
    global _client
    if _client is None:
        _client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    return _client

def get_sentiment_analyzer():
    global _sentiment_es
    if _sentiment_es is None:
        try:
            from pysentimiento import create_analyzer
            _sentiment_es = create_analyzer(task="sentiment", lang="es")
        except Exception:
            class DummyResult:
                output = "NEU"
                probas = {"POS": 0.33, "NEU": 0.34, "NEG": 0.33}
            class DummyAnalyzer:
                def predict(self, text): return DummyResult()
            _sentiment_es = DummyAnalyzer()
    return _sentiment_es


STOP_ES = {
    "si","no","tal","vez","quizás","gracias","ok","bueno","buenos",
    "bien","hola","buenas","nos","usted","ustedes","muy","solo","sólo"
}
DEMOGRAPHIC_HINTS = {
    "edad","años","género","genero","sexo","ciudad","región","region",
    "departamento","pais","país","provincia"
}
SCALE_5_TO_NPS = {5: "promotor", 4: "promotor", 3: "pasivo", 2: "detractor", 1: "detractor"}

# ═══════════════════════════════════════════════════════════
#                          HELPERS
# ═══════════════════════════════════════════════════════════
class _Utils:

    # --------------- KPIs ---------------
    @staticmethod
    def nps_weighted(nums: list[int], cats: list[str]) -> Optional[float]:
        """
        Conversión clásica:
        • 9-10 (o “promotor”) = +1
        • 7-8 (o “pasivo”)   = 0
        • 0-6 (o “detractor”) = -1
        """
        if not nums and not cats:
            return None
        score_num = sum(+1 if v >= 9 else -1 if v <= 6 else 0 for v in nums)
        weight    = {"promotor": 1, "detractor": -1, "pasivo": 0}
        score_txt = sum(weight[c] for c in cats)
        total     = len(nums) + len(cats)
        return round((score_num + score_txt) / total * 100, 1)

    @staticmethod
    def csat(nums: list[int]) -> Optional[float]:
        """% de respuestas 4-5 en escala 1-5 ó 8-10 en escala 1-10"""
        if not nums or np is None:
            return None
        nums_arr = np.array(nums)
        if nums_arr.max() <= 5:   # escala corta
            good = nums_arr >= 4
        else:
            good = nums_arr >= 8
        return round(good.mean() * 100, 1)

    # --------------- Series temporales ---------------
    @staticmethod
    def week_trend(df: Any, col: str, win: int = 4):
        """Media móvil semanal `win` semanas."""
        if df is None or df.empty:
            return []
        ts = (
            df.set_index("fecha")[col]
              .resample("W")
              .mean()
              .rolling(win)
              .mean()
              .dropna()
        )
        return ts.reset_index().to_dict("records")

    # --------------- LLM helpers ---------------
    @staticmethod
    def _chat(model: str, prompt: str) -> str:
        client = get_openai_client()
        return (
            client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                timeout=20,
            )
            .choices[0]
            .message
            .content
            .strip()
        )

    @classmethod
    def recommendations(cls, resume: str) -> str:
        prompt = (
            "Eres consultor de customer experience.\n\n"
            f"Resumen analítico:\n{resume}\n\n"
            "Devuelve EXACTAMENTE 5 acciones SMART (específicas, medibles, alcanzables, "
            "relevantes y acotadas en el tiempo) que la empresa debe realizar para mejorar. "
            "Usa un lenguaje sencillo, directo y empático. "
            "Respuesta en lista numerada.\n"
        )
        return cls._chat("gpt-4o", prompt)

    # --------------- Clasificación de preguntas ---------------
    @classmethod
    @functools.lru_cache(maxsize=256)
    def classify_question(cls, texto: str) -> str:
        """Clasifica ajustado localmente para evitar coste alto de llamadas."""
        txt = texto.lower()
        if any(h in txt for h in DEMOGRAPHIC_HINTS):
            return "demografica"
        if re.search(r"recom(endar|endarías|endarías)|nps|volverías", txt):
            return "recomendacion"
        if re.search(r"satisf[aá]cci[oó]n|agrado|content[ao]", txt):
            return "satisfaccion"
        if re.search(r"mejorar|cambiar|suger", txt):
            return "mejoras"
        if re.search(r"^.*(escala|califica|calificalo).*", txt):
            return "escala"
        return "libre"


# ═══════════════════════════════════════════════════════════
#                        NLP SERVICE
# ═══════════════════════════════════════════════════════════
class NLPAnalysisService:

    def __init__(self, db: Session):
        self.db = db
        self.ut = _Utils()

    def _fetch_rows(
        self,
        suscriptor_id: uuid.UUID,
        start: Optional[datetime],
        end: Optional[datetime],
        campana_id: Optional[uuid.UUID],
    ):
        q = (
            self.db.query(
                RespuestaPregunta,
                PreguntaEncuesta.tipo_pregunta_id,
                PreguntaEncuesta.texto.label("pregunta_txt"),
                PreguntaEncuesta.id.label("pregunta_id"),
                OpcionEncuesta.texto.label("opcion_txt"),
                RespuestaEncuesta.recibido_en,
                CampanaEncuesta.id.label("campana_id"),
                CampanaEncuesta.nombre.label("campana_nombre"),
                CampanaEncuesta.canal_id.label("campana_canal"),
            )
            .join(RespuestaEncuesta, RespuestaPregunta.respuesta_id == RespuestaEncuesta.id)
            .join(EntregaEncuesta, RespuestaEncuesta.entrega_id == EntregaEncuesta.id)
            .join(CampanaEncuesta, EntregaEncuesta.campana_id == CampanaEncuesta.id)
            .join(PreguntaEncuesta, RespuestaPregunta.pregunta_id == PreguntaEncuesta.id)
            .outerjoin(OpcionEncuesta, RespuestaPregunta.opcion_id == OpcionEncuesta.id)
            .filter(CampanaEncuesta.suscriptor_id == suscriptor_id)
        )

        if start:
            q = q.filter(RespuestaEncuesta.recibido_en >= start)
        if end:
            q = q.filter(RespuestaEncuesta.recibido_en <= end)
        if campana_id:
            q = q.filter(CampanaEncuesta.id == campana_id)

        return q.all()

    @staticmethod
    def _sentiment_stats(texts: List[str]) -> Dict[str, Any]:
        cats, scores = Counter(), []
        analyzer = get_sentiment_analyzer()
        for t in texts:
            r = analyzer.predict(t)
            cats[r.output] += 1
            scores.append(r.probas[r.output])
        total = sum(cats.values()) or 1
        mean_score = float(sum(scores) / len(scores)) if scores else 0
        return {
            "promedio": round(mean_score, 3),
            "positivo": cats["POS"],
            "neutro": cats["NEU"],
            "negativo": cats["NEG"],
            "distribucion": {
                k.lower(): round(v / total * 100, 2) for k, v in cats.items()
            },
        }

    @staticmethod
    def _txt_to_nps_cat(text: str, ctx: str, pos_th: float = 0.4, neg_th: float = 0.4) -> str:
        BAD = {
            "regular", "meh", "más o menos", "mas o menos", "nada",
            "podría mejorar", "podria mejorar", "flojo", "insuficiente",
            "decepcionado", "decepcionante"
        }
        if ctx == "demografica":
            return "pasivo"

        txt = text.lower()
        if any(b in txt for b in BAD):
            return "detractor"

        r = get_sentiment_analyzer().predict(text)
        pos, neg = r.probas["POS"], r.probas["NEG"]

        if ctx == "mejoras":
            return "detractor"
        if ctx in {"satisfaccion", "recomendacion", "escala"}:
            if pos >= pos_th:
                return "promotor"
            if neg >= neg_th:
                return "detractor"
            return "pasivo"

        if pos - neg >= 0.25:
            return "promotor"
        if neg - pos >= 0.15:
            return "detractor"
        return "pasivo"

    def _keywords(self, texts: List[str], top: int = 20) -> Dict[str, Any]:
        words = Counter(" ".join(texts).lower().split())
        filtered = [(w, c) for w, c in words.most_common(top) if w not in STOP_ES and len(w) > 2]
        return {
            "keywords": [
                {"palabra": w, "valor": float(c)} for w, c in filtered
            ]
        }

    def _topics(self, texts: List[str], n: int):
        return []

    def _clusters(self, texts: List[str], k_req: int):
        return {"clusters": [], "total_clusters": 0}

    def _analisis_pregunta(
        self,
        rows: List[Any],
        pid: str,
        ctx: str,
        p_dict: Dict[str, PreguntaEncuesta],
        pos_th: float,
        neg_th: float,
    ):
        sub = [r for r in rows if str(r.pregunta_id) == pid]
        p_obj = p_dict.get(pid)
        tipo = p_obj.tipo_pregunta_id if p_obj else (sub[0].tipo_pregunta_id if sub else None)

        res = OrderedDict(
            pregunta_id=pid,
            pregunta_texto=p_obj.texto if p_obj else "",
            total_respuestas=len(sub),
            tipo_pregunta=tipo,
            contexto=ctx,
        )

        if tipo == 1 and sub:
            txts = [r.RespuestaPregunta.texto for r in sub if r.RespuestaPregunta.texto]
            res["sentiment"] = self._sentiment_stats(txts)
            res["keywords"]  = self._keywords(txts)

        elif tipo == 2 and sub:
            nums = [
                float(r.RespuestaPregunta.numero)
                for r in sub
                if r.RespuestaPregunta.numero is not None
            ]
            if nums:
                res["estadisticas"] = {
                    "promedio": round(sum(nums) / len(nums), 2),
                    "mediana": round(sorted(nums)[len(nums)//2], 2),
                    "min": min(nums),
                    "max": max(nums),
                    "desviacion": 0.0,
                }

        elif tipo in {3, 4}:
            total_opts = [o.texto for o in p_obj.opciones] if p_obj else []
            cnt = Counter(r.opcion_txt for r in sub if r.opcion_txt)
            tot = sum(cnt.values()) or 1
            res["opciones"] = {
                "conteo": {opt: cnt.get(opt, 0) for opt in total_opts},
                "porcentajes": {opt: round(cnt.get(opt, 0) / tot * 100, 1) for opt in total_opts},
                "opciones_totales": total_opts,
            }
        return res

    async def analyze_responses(
        self,
        suscriptor_id: uuid.UUID,
        params: NLPAnalysisRequest,
    ) -> NLPAnalysisResponse:
        rows = self._fetch_rows(
            suscriptor_id, params.fecha_inicio, params.fecha_fin, params.campana_id
        )
        if not rows:
            raise HTTPException(status_code=404, detail="Sin respuestas")

        pos_th      = getattr(params, "umbral_sent_pos", 0.40)
        neg_th      = getattr(params, "umbral_sent_neg", 0.40)
        escala_corta = getattr(params, "escala_corta", False)

        p_objs = (
            self.db.query(PreguntaEncuesta)
            .filter(PreguntaEncuesta.id.in_({r.pregunta_id for r in rows}))
            .all()
        )
        p_dict = {str(p.id): p for p in p_objs}
        ctx_map = {str(p.id): _Utils.classify_question(p.texto) for p in p_objs}

        texts, nums, cats = [], [], []
        for r in rows:
            ctx = ctx_map.get(str(r.pregunta_id), "libre")

            if r.RespuestaPregunta.texto:
                texts.append(r.RespuestaPregunta.texto)
                cats.append(self._txt_to_nps_cat(r.RespuestaPregunta.texto, ctx, pos_th, neg_th))
            elif r.opcion_txt:
                cats.append(self._txt_to_nps_cat(r.opcion_txt, ctx, pos_th, neg_th))
                texts.append(r.opcion_txt)

            if r.tipo_pregunta_id == 2 and r.RespuestaPregunta.numero is not None:
                val = int(r.RespuestaPregunta.numero)
                if escala_corta and 1 <= val <= 5:
                    cats.append(SCALE_5_TO_NPS[val])
                else:
                    nums.append(val)

        sentiment_global = self._sentiment_stats(texts)
        sentiment_global["kpis"] = {
            "nps":  self.ut.nps_weighted(nums, cats),
            "csat": self.ut.csat(nums),
        }
        sentiment_global["trend"] = []

        topics   = self._topics(texts, max(1, min(3, params.num_topics)))
        clusters = self._clusters(texts, max(2, params.num_clusters))
        neg_kw   = [
            kw["palabra"] for kw in self._keywords(texts, top=25)["keywords"][:10]
            if kw["palabra"] not in STOP_ES
        ]

        resumen_llm = (
            f"NPS={sentiment_global['kpis']['nps']}; "
            f"CSAT={sentiment_global['kpis']['csat']}; "
            f"Top palabras negativas={', '.join(neg_kw)}; "
            f"Detractores={cats.count('detractor')}"
        )
        recs = self.ut.recommendations(resumen_llm)

        campanas = [
            {
                "id": cid,
                "nombre": next(n for n in {x.campana_nombre for x in rows if str(x.campana_id) == cid}),
                "total_respuestas": tot,
            }
            for cid, tot in Counter(str(r.campana_id) for r in rows).items()
        ]

        analisis_pregunta = [
            self._analisis_pregunta(rows, pid, ctx_map.get(pid, "libre"), p_dict, pos_th, neg_th)
            for pid in p_dict
        ]

        canales_cnt = Counter(r.campana_canal for r in rows)
        canales = {c: canales_cnt[c] for c in sorted(canales_cnt)}

        return {
            "suscriptor_id": str(suscriptor_id),
            "fecha_analisis": datetime.utcnow(),
            "periodo": {"inicio": params.fecha_inicio, "fin": params.fecha_fin},
            "total_respuestas": len(rows),
            "total_respuestas_texto": len(texts),
            "sentiment_global": sentiment_global,
            "topics": topics,
            "clusters": clusters,
            "analisis_por_pregunta": analisis_pregunta,
            "campanas": campanas,
            "canales": canales,
            "recommendations": recs,
        }

def get_nlp_service(db: Session) -> NLPAnalysisService:
    return NLPAnalysisService(db)
