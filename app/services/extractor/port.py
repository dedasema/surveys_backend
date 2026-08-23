from abc import ABC, abstractmethod
from typing import Dict, Any

class SurveyExtractorPort(ABC):
    """
    Puerto (interfaz abstracta) para la extracción estructurada de respuestas de encuestas
    desde archivos multimodales (imágenes de OCR o archivos de audio).
    """

    @abstractmethod
    def extract_from_image(
        self, 
        image_bytes: bytes, 
        mime_type: str, 
        plantilla_map: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Extrae el entrega_id (si está visible en QR/cabecera) y las respuestas escritas/marcadas
        en una imagen o escaneo de un formulario de papel.
        """
        pass

    @abstractmethod
    def extract_from_audio(
        self, 
        audio_bytes: bytes, 
        mime_type: str, 
        plantilla_map: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Transcribe el audio e interpreta las respuestas a las preguntas descritas en plantilla_map.
        """
        pass
