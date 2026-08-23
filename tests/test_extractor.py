import pytest
from uuid import uuid4
from app.services.extractor.port import SurveyExtractorPort
from app.services.extractor.gemini_adapter import GeminiExtractorService


class MockExtractorAdapter(SurveyExtractorPort):
    def extract_from_image(self, image_bytes: bytes, mime_type: str, plantilla_map: dict) -> dict:
        return {
            "entrega_id": str(uuid4()),
            "transcripcion": None,
            "respuestas_preguntas": [
                {
                    "pregunta_id": str(uuid4()),
                    "tipo_pregunta_id": 1,
                    "texto": "Respuesta OCR de prueba",
                    "numero": None,
                    "opcion_id": None,
                    "opciones_ids": []
                }
            ]
        }

    def extract_from_audio(self, audio_bytes: bytes, mime_type: str, plantilla_map: dict) -> dict:
        return {
            "entrega_id": None,
            "transcripcion": "Hola, mi satisfacción fue excelente",
            "respuestas_preguntas": [
                {
                    "pregunta_id": str(uuid4()),
                    "tipo_pregunta_id": 2,
                    "texto": None,
                    "numero": 5,
                    "opcion_id": None,
                    "opciones_ids": []
                }
            ]
        }


def test_extractor_port_contract():
    mock_extractor = MockExtractorAdapter()
    res_img = mock_extractor.extract_from_image(b"fake_image", "image/png", {})
    assert "entrega_id" in res_img
    assert len(res_img["respuestas_preguntas"]) == 1
    assert res_img["respuestas_preguntas"][0]["texto"] == "Respuesta OCR de prueba"

    res_audio = mock_extractor.extract_from_audio(b"fake_audio", "audio/mp3", {})
    assert res_audio["transcripcion"] == "Hola, mi satisfacción fue excelente"
    assert res_audio["respuestas_preguntas"][0]["numero"] == 5


def test_gemini_extractor_service_init():
    service = GeminiExtractorService(api_key="test_key", model="gemini-2.0-flash")
    assert service.api_key == "test_key"
    assert service.model == "gemini-2.0-flash"
    assert isinstance(service, SurveyExtractorPort)
