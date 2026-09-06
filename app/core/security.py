# app/core/security.py

import os
from datetime import datetime, timedelta

from jose import jwt, JWTError
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from uuid import UUID
from dotenv import load_dotenv

from app.core.database import get_db
from app.schemas.auth import TokenData
from app.models.cuenta_usuario import CuentaUsuario
from app.models.suscriptor import Suscriptor

# 1) Carga variables de entorno
load_dotenv()

# 2) Lee SECRET_KEY y valida
SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY or not isinstance(SECRET_KEY, str):
    raise RuntimeError("Debes definir SECRET_KEY en tu .env como un string")

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))

import hashlib
import secrets
from datetime import timezone

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
bearer_scheme = HTTPBearer()

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def hash_token(raw_token: str) -> str:
    """Calcula el hash SHA-256 de un token opaco para almacenamiento seguro"""
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()

def create_access_token(subject: str, role: str, permisos: list[str] = None) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode = {
        "sub": subject,
        "role": role,
        "permisos": permisos or [],
        "exp": expire
    }
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def create_refresh_token(db: Session, user_id: UUID) -> str:
    """Genera un refresh token criptográfico, guarda su hash en BD y devuelve el token en texto plano"""
    from app.models.refresh_token import RefreshToken
    from app.core.config import settings

    raw_token = secrets.token_urlsafe(64)
    token_hash = hash_token(raw_token)
    expira_en = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

    refresh_obj = RefreshToken(
        user_id=user_id,
        token_hash=token_hash,
        revocado=False,
        expira_en=expira_en,
        creado_en=datetime.now(timezone.utc)
    )
    db.add(refresh_obj)
    db.commit()
    db.refresh(refresh_obj)
    return raw_token

def rotate_refresh_token(db: Session, raw_token: str) -> tuple[any, str]:
    """Valida el refresh token, lo revoca e inmediatamente emite uno nuevo (rotación segura)"""
    from app.models.refresh_token import RefreshToken
    
    token_hash = hash_token(raw_token)
    ahora = datetime.now(timezone.utc)

    db_token = db.query(RefreshToken).filter(
        RefreshToken.token_hash == token_hash
    ).first()

    if not db_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token no encontrado"
        )
    if db_token.revocado:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="El refresh token ha sido revocado"
        )
    
    expira_comparable = db_token.expira_en
    if expira_comparable.tzinfo is None:
        expira_comparable = expira_comparable.replace(tzinfo=timezone.utc)

    if expira_comparable < ahora:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="El refresh token ha expirado"
        )

    # Revocamos el token actual
    db_token.revocado = True
    db.commit()

    # Emitimos nuevo refresh token
    nuevo_raw = create_refresh_token(db, db_token.user_id)
    return db_token, nuevo_raw

def revoke_refresh_token(db: Session, raw_token: str) -> bool:
    """Revoca un refresh token en el servidor para forzar un logout real"""
    from app.models.refresh_token import RefreshToken
    
    token_hash = hash_token(raw_token)
    db_token = db.query(RefreshToken).filter(RefreshToken.token_hash == token_hash).first()
    if db_token:
        db_token.revocado = True
        db.commit()
        return True
    return False

def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db)
) -> TokenData:
    token = credentials.credentials
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="No se pudo validar las credenciales",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        role_name: str = payload.get("role")
        permisos: list = payload.get("permisos", [])
        if user_id is None or role_name is None:
            raise credentials_exception
        return TokenData(sub=user_id, role=role_name, permisos=permisos)
    except JWTError:
        raise credentials_exception

def get_admin_user(token_data: TokenData = Depends(get_current_user)) -> TokenData:
    """Verifica que el usuario sea un administrador"""
    if token_data.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acceso denegado. Se requiere rol de administrador"
        )
    return token_data

def get_empresa_user(token_data: TokenData = Depends(get_current_user)) -> TokenData:
    """Verifica que el usuario tenga rol de empresa"""
    if token_data.role != "empresa":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acceso denegado. Se requiere rol de empresa"
        )
    return token_data

async def validate_subscriber_access(
    token_data: TokenData,
    suscriptor_id: UUID,
    db: Session = Depends(get_db)
) -> bool:
    """Valida que el usuario tenga acceso a los recursos del suscriptor"""
    if token_data.role == "admin":
        return True
    if token_data.role == "empresa" and str(token_data.sub).lower() == str(suscriptor_id).lower():
        return True
    elif token_data.role == "operator":
        try:
            op_uuid = UUID(token_data.sub) if isinstance(token_data.sub, str) else token_data.sub
            user = db.query(CuentaUsuario).filter(CuentaUsuario.id == op_uuid).first()
            if user and user.suscriptor_id and str(user.suscriptor_id).lower() == str(suscriptor_id).lower():
                return True
        except Exception:
            pass
    return False


def require_acceso_suscriptor_activo(
    token_data: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> TokenData:
    """Permite acceso si la empresa asociada tiene suscripción activa o si es admin"""
    if token_data.role == "admin":
        return token_data

    suscriptor_id = None

    if token_data.role == "empresa":
        suscriptor_id = token_data.sub
    elif token_data.role == "operator":
        try:
            op_uuid = UUID(token_data.sub) if isinstance(token_data.sub, str) else token_data.sub
            user = db.query(CuentaUsuario).filter(CuentaUsuario.id == op_uuid).first()
            if user and user.suscriptor_id:
                suscriptor_id = str(user.suscriptor_id)
        except Exception:
            pass

    if not suscriptor_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No se encontró el suscriptor asociado al usuario"
        )

    try:
        s_uuid = UUID(suscriptor_id) if isinstance(suscriptor_id, str) else suscriptor_id
    except Exception:
        raise HTTPException(status_code=400, detail="ID de suscriptor inválido")

    suscriptor = db.query(Suscriptor).filter_by(id=s_uuid).first()
    if not suscriptor or suscriptor.estado != "activo":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tu suscripción no está activa o fue cancelada."
        )

    return token_data


def require_permission(permission_code: str):
    """
    Dependencia reutilizable para endpoints que exigen un permiso granular específico.
    Administradores siempre tienen acceso implícito. Para otros roles, verifica que el rol
    tenga asignado el permiso_code en la tabla rol_permiso.
    """
    def dependency(
        token_data: TokenData = Depends(get_current_user),
        db: Session = Depends(get_db)
    ) -> TokenData:
        if token_data.role == "admin":
            return token_data

        if token_data.permisos and permission_code in token_data.permisos:
            return token_data

        from app.models.catalogos import Rol
        rol = db.query(Rol).filter(Rol.nombre == token_data.role).first()
        if not rol:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Rol de usuario no reconocido o inactivo"
            )

        codigos_asignados = {p.codigo for p in rol.permisos}
        if permission_code not in codigos_asignados:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Acceso denegado. Se requiere el permiso: '{permission_code}'"
            )

        return token_data

    return dependency
