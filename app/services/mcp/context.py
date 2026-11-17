# app/services/mcp/context.py
from dataclasses import dataclass, field
from typing import Optional, List
from uuid import UUID

@dataclass
class ActorContext:
    """
    Contexto de seguridad y autorización del actor que invoca herramientas MCP.
    Garantiza aislamiento multi-tenant estricto forzando suscriptor_id en todas las consultas.
    """
    user_id: UUID
    role: str  # 'empresa', 'admin', 'operator', 'analista'
    suscriptor_id: Optional[UUID] = None
    email: Optional[str] = None
    nombre: Optional[str] = None
    permisos: List[str] = field(default_factory=list)

    def es_admin(self) -> bool:
        return self.role == "admin"

    def es_empresa(self) -> bool:
        return self.role in ("empresa", "suscriptor")

    def requiere_suscriptor_id(self) -> UUID:
        if not self.suscriptor_id:
            raise PermissionError("Acción requiere un suscriptor_id válido y autenticado.")
        return self.suscriptor_id

def resolver_actor_context(db, token_data) -> ActorContext:
    """
    Construye el ActorContext a partir del TokenData decodificado y la sesión de base de datos.
    """
    from app.models.suscriptor import Suscriptor
    from app.models.cuenta_usuario import CuentaUsuario

    user_uuid = UUID(str(token_data.sub))
    role = token_data.role.lower()
    permisos = token_data.permisos or []

    suscriptor_id = None
    email = None
    nombre = None

    if role in ("empresa", "suscriptor"):
        suscriptor = db.query(Suscriptor).filter_by(id=user_uuid).first()
        if suscriptor:
            suscriptor_id = suscriptor.id
            email = suscriptor.email
            nombre = suscriptor.nombre
        else:
            suscriptor_id = user_uuid
    elif role == "admin":
        suscriptor_id = None
    else:
        # Cuenta de operador o analista
        cuenta = db.query(CuentaUsuario).filter_by(id=user_uuid).first()
        if cuenta:
            suscriptor_id = cuenta.suscriptor_id
            email = cuenta.email
            nombre = cuenta.nombre

    return ActorContext(
        user_id=user_uuid,
        role=role,
        suscriptor_id=suscriptor_id,
        email=email,
        nombre=nombre,
        permisos=permisos
    )

