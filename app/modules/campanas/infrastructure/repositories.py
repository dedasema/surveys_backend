"""
SQLAlchemy Implementation of ICampanaRepository (Adapter).
Converts between ORM models and Domain Entities.
"""

from typing import List, Optional
from uuid import UUID
from sqlalchemy.orm import Session

from app.models.survey import CampanaEncuesta
from app.modules.campanas.domain.entities import Campana, EstadoCampanaEnum
from app.modules.campanas.domain.repositories import ICampanaRepository


class SqlAlchemyCampanaRepository(ICampanaRepository):
    def __init__(self, db: Session):
        self.db = db

    def _to_domain(self, orm: CampanaEncuesta) -> Campana:
        return Campana(
            id=orm.id,
            suscriptor_id=orm.suscriptor_id,
            nombre=orm.nombre,
            plantilla_id=orm.plantilla_id,
            canal_id=orm.canal_id,
            estado_id=orm.estado_id,
            programada_en=orm.programada_en,
            creado_en=orm.creado_en,
        )

    def _to_orm(self, domain: Campana, orm: Optional[CampanaEncuesta] = None) -> CampanaEncuesta:
        if orm is None:
            orm = CampanaEncuesta(id=domain.id, suscriptor_id=domain.suscriptor_id)
        
        orm.nombre = domain.nombre
        orm.plantilla_id = domain.plantilla_id
        orm.canal_id = domain.canal_id
        orm.estado_id = domain.estado_id
        orm.programada_en = domain.programada_en
        return orm

    def get_by_id(self, campana_id: UUID) -> Optional[Campana]:
        orm = self.db.query(CampanaEncuesta).filter(CampanaEncuesta.id == campana_id).first()
        return self._to_domain(orm) if orm else None

    def list_by_suscriptor(self, suscriptor_id: UUID) -> List[Campana]:
        orms = (
            self.db.query(CampanaEncuesta)
            .filter(CampanaEncuesta.suscriptor_id == suscriptor_id)
            .all()
        )
        return [self._to_domain(o) for o in orms]

    def list_programadas_pendientes(self) -> List[Campana]:
        orms = (
            self.db.query(CampanaEncuesta)
            .filter(CampanaEncuesta.estado_id == EstadoCampanaEnum.PROGRAMADA)
            .all()
        )
        return [self._to_domain(o) for o in orms]

    def save(self, campana: Campana) -> Campana:
        orm = self.db.query(CampanaEncuesta).filter(CampanaEncuesta.id == campana.id).first()
        if orm:
            self._to_orm(campana, orm)
        else:
            orm = self._to_orm(campana)
            self.db.add(orm)

        self.db.commit()
        self.db.refresh(orm)
        return self._to_domain(orm)

    def delete(self, campana_id: UUID) -> bool:
        orm = self.db.query(CampanaEncuesta).filter(CampanaEncuesta.id == campana_id).first()
        if not orm:
            return False
        self.db.delete(orm)
        self.db.commit()
        return True
