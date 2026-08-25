"""
SQLAlchemy Repository Adapters for Entregas and Destinatarios.
"""

from typing import List, Optional
from uuid import UUID
from sqlalchemy.orm import Session

from app.models.survey import EntregaEncuesta, Destinatario as DestinatarioORM
from app.modules.entregas.domain.entities import Entrega, Destinatario
from app.modules.entregas.domain.repositories import IEntregaRepository, IDestinatarioRepository


class SqlAlchemyEntregaRepository(IEntregaRepository):
    def __init__(self, db: Session):
        self.db = db

    def _to_domain(self, orm: EntregaEncuesta) -> Entrega:
        return Entrega(
            id=orm.id,
            campana_id=orm.campana_id,
            destinatario_id=orm.destinatario_id,
            canal_id=orm.canal_id,
            estado_id=orm.estado_id,
            enviado_en=orm.enviado_en,
            respondido_en=orm.respondido_en,
        )

    def _to_orm(self, domain: Entrega, orm: Optional[EntregaEncuesta] = None) -> EntregaEncuesta:
        if orm is None:
            orm = EntregaEncuesta(
                id=domain.id,
                campana_id=domain.campana_id,
                canal_id=domain.canal_id,
            )
        orm.destinatario_id = domain.destinatario_id
        orm.canal_id = domain.canal_id
        orm.estado_id = domain.estado_id
        orm.enviado_en = domain.enviado_en
        orm.respondido_en = domain.respondido_en
        return orm

    def get_by_id(self, entrega_id: UUID) -> Optional[Entrega]:
        orm = self.db.query(EntregaEncuesta).filter(EntregaEncuesta.id == entrega_id).first()
        return self._to_domain(orm) if orm else None

    def list_by_campana(self, campana_id: UUID) -> List[Entrega]:
        orms = self.db.query(EntregaEncuesta).filter(EntregaEncuesta.campana_id == campana_id).all()
        return [self._to_domain(o) for o in orms]

    def save(self, entrega: Entrega) -> Entrega:
        orm = self.db.query(EntregaEncuesta).filter(EntregaEncuesta.id == entrega.id).first()
        if orm:
            self._to_orm(entrega, orm)
        else:
            orm = self._to_orm(entrega)
            self.db.add(orm)
        self.db.commit()
        self.db.refresh(orm)
        return self._to_domain(orm)

    def save_bulk(self, entregas: List[Entrega]) -> List[Entrega]:
        orms = [self._to_orm(e) for e in entregas]
        self.db.add_all(orms)
        self.db.commit()
        for o in orms:
            self.db.refresh(o)
        return [self._to_domain(o) for o in orms]

    def delete(self, entrega_id: UUID) -> bool:
        orm = self.db.query(EntregaEncuesta).filter(EntregaEncuesta.id == entrega_id).first()
        if not orm:
            return False
        self.db.delete(orm)
        self.db.commit()
        return True


class SqlAlchemyDestinatarioRepository(IDestinatarioRepository):
    def __init__(self, db: Session):
        self.db = db

    def _to_domain(self, orm: DestinatarioORM) -> Destinatario:
        return Destinatario(
            id=orm.id,
            suscriptor_id=orm.suscriptor_id,
            nombre=orm.nombre,
            email=orm.email,
            telefono=orm.telefono,
            creado_en=orm.creado_en,
        )

    def _to_orm(self, domain: Destinatario, orm: Optional[DestinatarioORM] = None) -> DestinatarioORM:
        if orm is None:
            orm = DestinatarioORM(id=domain.id, suscriptor_id=domain.suscriptor_id)
        orm.nombre = domain.nombre
        orm.email = domain.email
        orm.telefono = domain.telefono
        return orm

    def get_by_id(self, destinatario_id: UUID) -> Optional[Destinatario]:
        orm = self.db.query(DestinatarioORM).filter(DestinatarioORM.id == destinatario_id).first()
        return self._to_domain(orm) if orm else None

    def list_by_suscriptor(self, suscriptor_id: UUID) -> List[Destinatario]:
        orms = self.db.query(DestinatarioORM).filter(DestinatarioORM.suscriptor_id == suscriptor_id).all()
        return [self._to_domain(o) for o in orms]

    def save(self, destinatario: Destinatario) -> Destinatario:
        orm = self.db.query(DestinatarioORM).filter(DestinatarioORM.id == destinatario.id).first()
        if orm:
            self._to_orm(destinatario, orm)
        else:
            orm = self._to_orm(destinatario)
            self.db.add(orm)
        self.db.commit()
        self.db.refresh(orm)
        return self._to_domain(orm)

    def delete(self, destinatario_id: UUID) -> bool:
        orm = self.db.query(DestinatarioORM).filter(DestinatarioORM.id == destinatario_id).first()
        if not orm:
            return False
        self.db.delete(orm)
        self.db.commit()
        return True
