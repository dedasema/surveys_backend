"""
Domain Entities for Plantilla Aggregate (Plantilla -> Pregunta -> Opcion).
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional
from uuid import UUID, uuid4

from app.modules.plantillas.domain.exceptions import PlantillaDomainError


@dataclass
class Opcion:
    id: UUID
    pregunta_id: UUID
    texto: str
    valor: Optional[str] = None

    def __post_init__(self):
        if not self.texto or not self.texto.strip():
            raise PlantillaDomainError("El texto de la opción no puede estar vacío.")


@dataclass
class Pregunta:
    id: UUID
    plantilla_id: UUID
    texto: str
    tipo_pregunta_id: int
    obligatorio: bool = True
    orden: int = 1
    opciones: List[Opcion] = field(default_factory=list)

    def __post_init__(self):
        if not self.texto or not self.texto.strip():
            raise PlantillaDomainError("El texto de la pregunta no puede estar vacío.")
        if self.tipo_pregunta_id <= 0:
            raise PlantillaDomainError("El tipo_pregunta_id debe ser un identificador válido mayor a 0.")

    def agregar_opcion(self, texto: str, valor: Optional[str] = None) -> Opcion:
        opcion = Opcion(
            id=uuid4(),
            pregunta_id=self.id,
            texto=texto,
            valor=valor,
        )
        self.opciones.append(opcion)
        return opcion


@dataclass
class Plantilla:
    suscriptor_id: UUID
    nombre: str
    id: UUID = field(default_factory=uuid4)
    descripcion: Optional[str] = None
    creado_en: Optional[datetime] = None
    preguntas: List[Pregunta] = field(default_factory=list)

    def __post_init__(self):
        if not self.nombre or not self.nombre.strip():
            raise PlantillaDomainError("El nombre de la plantilla no puede estar vacío.")

    def actualizar(self, nombre: Optional[str] = None, descripcion: Optional[str] = None) -> None:
        if nombre is not None:
            if not nombre.strip():
                raise PlantillaDomainError("El nombre de la plantilla no puede estar vacío.")
            self.nombre = nombre
        if descripcion is not None:
            self.descripcion = descripcion

    def agregar_pregunta(
        self,
        texto: str,
        tipo_pregunta_id: int,
        obligatorio: bool = True,
        orden: Optional[int] = None,
    ) -> Pregunta:
        next_order = orden if orden is not None else (len(self.preguntas) + 1)
        pregunta = Pregunta(
            id=uuid4(),
            plantilla_id=self.id,
            texto=texto,
            tipo_pregunta_id=tipo_pregunta_id,
            obligatorio=obligatorio,
            orden=next_order,
        )
        self.preguntas.append(pregunta)
        return pregunta
