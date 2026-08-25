"""
SQLAlchemy Repositories (Adapters) for Plantilla, Pregunta, and Opcion.
"""

from typing import List, Optional
from uuid import UUID
from sqlalchemy.orm import Session, joinedload

from app.models.survey import PlantillaEncuesta, PreguntaEncuesta, OpcionEncuesta
from app.modules.plantillas.domain.entities import Plantilla, Pregunta, Opcion
from app.modules.plantillas.domain.repositories import (
    IPlantillaRepository,
    IPreguntaRepository,
    IOpcionRepository,
)


class SqlAlchemyPlantillaRepository(IPlantillaRepository):
    def __init__(self, db: Session):
        self.db = db

    def _to_domain(self, orm: PlantillaEncuesta, include_children: bool = False) -> Plantilla:
        preguntas = []
        if include_children and hasattr(orm, "preguntas") and orm.preguntas:
            for p_orm in orm.preguntas:
                opciones = [
                    Opcion(
                        id=o.id,
                        pregunta_id=o.pregunta_id,
                        texto=o.texto,
                        valor=o.valor,
                    )
                    for o in getattr(p_orm, "opciones", [])
                ]
                preguntas.append(
                    Pregunta(
                        id=p_orm.id,
                        plantilla_id=p_orm.plantilla_id,
                        texto=p_orm.texto,
                        tipo_pregunta_id=p_orm.tipo_pregunta_id,
                        obligatorio=p_orm.obligatorio,
                        orden=p_orm.orden,
                        opciones=opciones,
                    )
                )
        return Plantilla(
            id=orm.id,
            suscriptor_id=orm.suscriptor_id,
            nombre=orm.nombre,
            descripcion=orm.descripcion,
            creado_en=orm.creado_en,
            preguntas=preguntas,
        )

    def _to_orm(self, domain: Plantilla, orm: Optional[PlantillaEncuesta] = None) -> PlantillaEncuesta:
        if orm is None:
            orm = PlantillaEncuesta(id=domain.id, suscriptor_id=domain.suscriptor_id)
        orm.nombre = domain.nombre
        orm.descripcion = domain.descripcion
        return orm

    def get_by_id(self, plantilla_id: UUID) -> Optional[Plantilla]:
        orm = self.db.query(PlantillaEncuesta).filter(PlantillaEncuesta.id == plantilla_id).first()
        return self._to_domain(orm, include_children=False) if orm else None

    def get_con_preguntas(self, plantilla_id: UUID) -> Optional[Plantilla]:
        orm = (
            self.db.query(PlantillaEncuesta)
            .options(
                joinedload(PlantillaEncuesta.preguntas).joinedload(PreguntaEncuesta.opciones)
            )
            .filter(PlantillaEncuesta.id == plantilla_id)
            .first()
        )
        return self._to_domain(orm, include_children=True) if orm else None

    def list_by_suscriptor(self, suscriptor_id: UUID) -> List[Plantilla]:
        orms = (
            self.db.query(PlantillaEncuesta)
            .filter(PlantillaEncuesta.suscriptor_id == suscriptor_id)
            .all()
        )
        return [self._to_domain(o) for o in orms]

    def save(self, plantilla: Plantilla) -> Plantilla:
        orm = self.db.query(PlantillaEncuesta).filter(PlantillaEncuesta.id == plantilla.id).first()
        if orm:
            self._to_orm(plantilla, orm)
        else:
            orm = self._to_orm(plantilla)
            self.db.add(orm)
        self.db.commit()
        self.db.refresh(orm)
        return self._to_domain(orm)

    def delete(self, plantilla_id: UUID) -> bool:
        orm = self.db.query(PlantillaEncuesta).filter(PlantillaEncuesta.id == plantilla_id).first()
        if not orm:
            return False
        self.db.delete(orm)
        self.db.commit()
        return True


class SqlAlchemyPreguntaRepository(IPreguntaRepository):
    def __init__(self, db: Session):
        self.db = db

    def _to_domain(self, orm: PreguntaEncuesta) -> Pregunta:
        opciones = [
            Opcion(id=o.id, pregunta_id=o.pregunta_id, texto=o.texto, valor=o.valor)
            for o in getattr(orm, "opciones", [])
        ]
        return Pregunta(
            id=orm.id,
            plantilla_id=orm.plantilla_id,
            texto=orm.texto,
            tipo_pregunta_id=orm.tipo_pregunta_id,
            obligatorio=orm.obligatorio,
            orden=orm.orden,
            opciones=opciones,
        )

    def get_by_id(self, pregunta_id: UUID) -> Optional[Pregunta]:
        orm = (
            self.db.query(PreguntaEncuesta)
            .options(joinedload(PreguntaEncuesta.opciones))
            .filter(PreguntaEncuesta.id == pregunta_id)
            .first()
        )
        return self._to_domain(orm) if orm else None

    def list_by_plantilla(self, plantilla_id: UUID) -> List[Pregunta]:
        orms = (
            self.db.query(PreguntaEncuesta)
            .options(joinedload(PreguntaEncuesta.opciones))
            .filter(PreguntaEncuesta.plantilla_id == plantilla_id)
            .order_by(PreguntaEncuesta.orden)
            .all()
        )
        return [self._to_domain(o) for o in orms]

    def save(self, pregunta: Pregunta) -> Pregunta:
        orm = self.db.query(PreguntaEncuesta).filter(PreguntaEncuesta.id == pregunta.id).first()
        if orm:
            orm.texto = pregunta.texto
            orm.tipo_pregunta_id = pregunta.tipo_pregunta_id
            orm.obligatorio = pregunta.obligatorio
            orm.orden = pregunta.orden
        else:
            orm = PreguntaEncuesta(
                id=pregunta.id,
                plantilla_id=pregunta.plantilla_id,
                texto=pregunta.texto,
                tipo_pregunta_id=pregunta.tipo_pregunta_id,
                obligatorio=pregunta.obligatorio,
                orden=pregunta.orden,
            )
            self.db.add(orm)
        self.db.commit()
        self.db.refresh(orm)
        return self._to_domain(orm)

    def delete(self, pregunta_id: UUID) -> bool:
        orm = self.db.query(PreguntaEncuesta).filter(PreguntaEncuesta.id == pregunta_id).first()
        if not orm:
            return False
        self.db.delete(orm)
        self.db.commit()
        return True


class SqlAlchemyOpcionRepository(IOpcionRepository):
    def __init__(self, db: Session):
        self.db = db

    def _to_domain(self, orm: OpcionEncuesta) -> Opcion:
        return Opcion(
            id=orm.id,
            pregunta_id=orm.pregunta_id,
            texto=orm.texto,
            valor=orm.valor,
        )

    def get_by_id(self, opcion_id: UUID) -> Optional[Opcion]:
        orm = self.db.query(OpcionEncuesta).filter(OpcionEncuesta.id == opcion_id).first()
        return self._to_domain(orm) if orm else None

    def list_by_pregunta(self, pregunta_id: UUID) -> List[Opcion]:
        orms = (
            self.db.query(OpcionEncuesta)
            .filter(OpcionEncuesta.pregunta_id == pregunta_id)
            .all()
        )
        return [self._to_domain(o) for o in orms]

    def save(self, opcion: Opcion) -> Opcion:
        orm = self.db.query(OpcionEncuesta).filter(OpcionEncuesta.id == opcion.id).first()
        if orm:
            orm.texto = opcion.texto
            orm.valor = opcion.valor
        else:
            orm = OpcionEncuesta(
                id=opcion.id,
                pregunta_id=opcion.pregunta_id,
                texto=opcion.texto,
                valor=opcion.valor,
            )
            self.db.add(orm)
        self.db.commit()
        self.db.refresh(orm)
        return self._to_domain(orm)

    def delete(self, opcion_id: UUID) -> bool:
        orm = self.db.query(OpcionEncuesta).filter(OpcionEncuesta.id == opcion_id).first()
        if not orm:
            return False
        self.db.delete(orm)
        self.db.commit()
        return True
