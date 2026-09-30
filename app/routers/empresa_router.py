# app/routers/empresa_router.py
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from uuid import UUID
from typing import Optional

from app.core.database import get_db
from app.core.security import get_current_user, TokenData
from app.models.cuenta_usuario import CuentaUsuario
from app.models.suscriptor import Suscriptor
from app.schemas.uso_sistema import UsoSistemaResponse
from app.services.uso_sistema_service import obtener_uso_sistema_empresa

router = APIRouter(
    prefix="/empresa",
    tags=["Empresa"],
    dependencies=[Depends(get_current_user)]
)

def _resolver_tenant_id(
    db: Session,
    token_data: TokenData,
    suscriptor_id: Optional[UUID] = None
) -> UUID:
    if token_data.role == "empresa":
        return UUID(token_data.sub)
    elif token_data.role in ["operator", "empresa_operador"]:
        cuenta = db.query(CuentaUsuario).filter(CuentaUsuario.id == UUID(token_data.sub)).first()
        if not cuenta:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cuenta de usuario no encontrada")
        return cuenta.suscriptor_id
    elif token_data.role == "admin":
        if suscriptor_id:
            return suscriptor_id
        primer_sus = db.query(Suscriptor).first()
        if not primer_sus:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No existen empresas registradas")
        return primer_sus.id
    else:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No tienes permisos para acceder a estos datos")

@router.get("/uso-sistema", response_model=UsoSistemaResponse)
def get_empresa_uso_sistema(
    dias: int = Query(30, ge=1, le=365, description="Ventana de tiempo en días"),
    suscriptor_id: Optional[UUID] = Query(None, description="ID del suscriptor (solo para rol admin)"),
    token_data: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Obtiene las métricas de uso del sistema de la empresa:
    - Última sesión
    - Espacio usado (MB, límite y porcentaje)
    - Total de pagos realizados a la fecha y frecuencia
    - Gráfica temporal con días de mayor uso
    - Top 5 usuarios más activos
    - Distribución CUD (Crear, Modificar, Eliminar)
    """
    tenant_id = _resolver_tenant_id(db, token_data, suscriptor_id)
    return obtener_uso_sistema_empresa(db=db, suscriptor_id=tenant_id, dias=dias)
