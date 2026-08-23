import json
import logging
import re
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field

from app.core.config import settings
from app.services.extractor.port import SurveyExtractorPort

logger = logging.getLogger(__name__)


class RespuestaItemSchema(BaseModel):
    pregunta_id: str
    tipo_pregunta_id: int
    texto: Optional[str] = None
    numero: Optional[float] = None
    opcion_id: Optional[str] = None
    opciones_ids: Optional[List[str]] = Field(default_factory=list)


class ExtractionResultSchema(BaseModel):
    entrega_id: Optional[str] = None
    transcripcion: Optional[str] = None
    respuestas_preguntas: List[RespuestaItemSchema] = Field(default_factory=list)


class GeminiExtractorService(SurveyExtractorPort):
    """
    Adaptador concreto para la extracción multimodal estructurada de respuestas
    usando el SDK oficial google-genai de Google Gemini.
    """

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.api_key = (api_key or settings.GEMINI_API_KEY or "").strip()
        self.model = model or settings.GEMINI_MODEL or "gemini-2.0-flash"

    def _get_genai_client(self):
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY no está configurada en las variables de entorno")
        try:
            from google import genai
            return genai.Client(api_key=self.api_key)
        except ImportError as e:
            logger.error("No se pudo importar google-genai SDK: %s", e)
            raise RuntimeError("La librería 'google-genai' no está instalada. Ejecute 'pip install google-genai'") from e

    def _parse_json_response(self, text_content: str) -> Dict[str, Any]:
        """Limpia bloques de código markdown ```json y parsea la respuesta JSON."""
        cleaned = text_content.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\n?", "", cleaned, flags=re.IGNORECASE)
            cleaned = re.sub(r"\n?```$", "", cleaned)
        try:
            return json.loads(cleaned.strip())
        except json.JSONDecodeError as err:
            logger.error("Error al decodificar JSON de Gemini: %s. Texto crudo: %s", err, text_content)
            return {"respuestas_preguntas": []}

    def extract_from_image(
        self, 
        image_bytes: bytes, 
        mime_type: str, 
        plantilla_map: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Extrae respuestas de un formulario en papel/imagen (OCR) usando Gemini Multimodal.
        """
        client = self._get_genai_client()
        from google.genai import types

        prompt = (
            "Eres un extractor OCR especializado en formularios de encuestas.\n"
            "Analiza detenidamente la imagen adjunta:\n"
            "1. Si el formulario contiene un código QR o un identificador de entrega (UUID) en el encabezado/borde, extráelo en 'entrega_id'. Si no existe, usa null.\n"
            "2. Examina las respuestas marcadas o escritas a mano/texto para cada pregunta descrita en la plantilla.\n"
            "3. Mapea cada respuesta al 'pregunta_id' correspondiente según las siguientes reglas:\n"
            "   - Pregunta Abierta / Texto (tipo 1): coloca el texto extraído en 'texto'.\n"
            "   - Pregunta Numérica / Escala (tipo 2): coloca el valor numérico en 'numero'.\n"
            "   - Pregunta Selección Única (tipo 3): coloca el UUID de la opción marcada en 'opcion_id'.\n"
            "   - Pregunta Selección Múltiple (tipo 4): coloca una lista con los UUIDs de las opciones marcadas en 'opciones_ids'.\n\n"
            f"Plantilla de Preguntas y Opciones Válidas:\n{json.dumps(plantilla_map, ensure_ascii=False, indent=2)}\n\n"
            "Responde estrictamente en formato JSON."
        )

        image_part = types.Part.from_bytes(data=image_bytes, mime_type=mime_type or "image/jpeg")
        config = types.GenerateContentConfig(
            temperature=0.1,
            response_mime_type="application/json",
            response_schema=ExtractionResultSchema,
        )

        try:
            response = client.models.generate_content(
                model=self.model,
                contents=[image_part, prompt],
                config=config,
            )
            return self._parse_json_response(response.text)
        except Exception as exc:
            logger.error("Error durante la extracción OCR en Gemini: %s", exc)
            raise RuntimeError(f"Error al procesar imagen con Gemini: {exc}") from exc

    def extract_from_audio(
        self, 
        audio_bytes: bytes, 
        mime_type: str, 
        plantilla_map: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Transcribe e interpreta respuestas de una grabación de audio usando Gemini Multimodal.
        """
        client = self._get_genai_client()
        from google.genai import types

        prompt = (
            "Eres un asistente analista de encuestas por voz.\n"
            "Escucha con atención el archivo de audio adjunto:\n"
            "1. Transcribe íntegramente todo el contenido hablado y colócalo en 'transcripcion'.\n"
            "2. Analiza lo expresado por el hablante e interpreta sus respuestas para cada pregunta descrita en la plantilla.\n"
            "3. Mapea cada respuesta al 'pregunta_id' correspondiente siguiendo estas reglas:\n"
            "   - Pregunta Abierta / Texto (tipo 1): coloca la respuesta hablada en 'texto'.\n"
            "   - Pregunta Numérica / Escala (tipo 2): coloca el valor numérico deducido en 'numero'.\n"
            "   - Pregunta Selección Única (tipo 3): identifica la opción elegida y coloca su UUID en 'opcion_id'.\n"
            "   - Pregunta Selección Múltiple (tipo 4): coloca la lista de UUIDs de las opciones elegidas en 'opciones_ids'.\n\n"
            f"Plantilla de Preguntas y Opciones Válidas:\n{json.dumps(plantilla_map, ensure_ascii=False, indent=2)}\n\n"
            "Responde estrictamente en formato JSON."
        )

        audio_part = types.Part.from_bytes(data=audio_bytes, mime_type=mime_type or "audio/mp3")
        config = types.GenerateContentConfig(
            temperature=0.1,
            response_mime_type="application/json",
            response_schema=ExtractionResultSchema,
        )

        try:
            response = client.models.generate_content(
                model=self.model,
                contents=[audio_part, prompt],
                config=config,
            )
            return self._parse_json_response(response.text)
        except Exception as exc:
            logger.error("Error durante la extracción de Audio en Gemini: %s", exc)
            raise RuntimeError(f"Error al procesar audio con Gemini: {exc}") from exc
