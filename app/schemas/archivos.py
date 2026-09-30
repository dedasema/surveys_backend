# app/schemas/archivos.py
from pydantic import BaseModel, ConfigDict
from typing import Optional, List, Dict, Any

class ArchivoItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    archivo: str
    extension: str
    peso: float
    unidad: str
    peso_bytes: int
    url_descarga: str
    opcion_ver_descargar: Dict[str, Any]
    mime_type: str
    categoria: str
    contexto: Optional[str] = None
    fecha_subida: str
    creado_por: Optional[str] = None

class ArchivosListResponse(BaseModel):
    total: int
    limit: int
    offset: int
    espacio_total_usado_mb: float
    archivos: List[ArchivoItemOut]
