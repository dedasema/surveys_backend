from sqlalchemy import Column, Integer, String, Table, ForeignKey
from sqlalchemy.orm import relationship
from app.core.database import Base

rol_permiso = Table(
    "rol_permiso",
    Base.metadata,
    Column("rol_id", Integer, ForeignKey("rol.id", ondelete="CASCADE"), primary_key=True),
    Column("permiso_id", Integer, ForeignKey("permiso.id", ondelete="CASCADE"), primary_key=True),
)

class Permiso(Base):
    __tablename__ = "permiso"
    id          = Column(Integer, primary_key=True, index=True)
    codigo      = Column(String, nullable=False, unique=True, index=True)
    nombre      = Column(String, nullable=False)
    modulo      = Column(String, nullable=False)
    descripcion = Column(String, nullable=True)

    roles = relationship("Rol", secondary=rol_permiso, back_populates="permisos")

class Rol(Base):
    __tablename__ = "rol"
    id          = Column(Integer, primary_key=True, index=True)
    nombre      = Column(String, nullable=False, unique=True)
    descripcion = Column(String, nullable=True)

    permisos = relationship("Permiso", secondary=rol_permiso, back_populates="roles")

class TipoPregunta(Base):
    __tablename__ = "tipo_pregunta"
    id     = Column(Integer, primary_key=True, index=True)
    nombre = Column(String, nullable=False, unique=True)

class Canal(Base):
    __tablename__ = "canal"
    id     = Column(Integer, primary_key=True, index=True)
    nombre = Column(String, nullable=False, unique=True)

class EstadoCampana(Base):
    __tablename__ = "estado_campana"
    id     = Column(Integer, primary_key=True, index=True)
    nombre = Column(String, nullable=False, unique=True)

class EstadoEntrega(Base):
    __tablename__ = "estado_entrega"
    id     = Column(Integer, primary_key=True, index=True)
    nombre = Column(String, nullable=False, unique=True)

class EstadoDocumento(Base):
    __tablename__ = "estado_documento"
    id     = Column(Integer, primary_key=True, index=True)
    nombre = Column(String, nullable=False, unique=True)

class EstadoPago(Base):
    __tablename__ = "estado_pago"
    id     = Column(Integer, primary_key=True, index=True)
    nombre = Column(String, nullable=False, unique=True)

class MetodoPago(Base):
    __tablename__ = "metodo_pago"
    id     = Column(Integer, primary_key=True, index=True)
    nombre = Column(String, nullable=False, unique=True)
