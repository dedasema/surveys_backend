# app/routers/auth.py

import logging
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, status, Body, UploadFile, File, Query
from sqlalchemy.orm import Session
from fastapi.security import OAuth2PasswordRequestForm

logger = logging.getLogger(__name__)

from app.core.database import get_db
from app.core.security import (
    hash_password, verify_password, create_access_token, get_current_user,
    create_refresh_token, rotate_refresh_token, revoke_refresh_token
)
from app.core.config import settings

from app.models.catalogos import Rol
from app.models.administrador import Administrador
from app.models.suscriptor import Suscriptor
from app.models.cuenta_usuario import CuentaUsuario

from app.schemas.auth import (
    AdminCreate, AdminOut, AdminProfileOut, AdminUpdateRequest, ForgotPasswordRequest, LoginRequest, OperatorProfileOut, OperatorUpdateRequest, ResetPasswordRequest,
    SuscriptorCreate, SuscriptorOut,
    CuentaUsuarioCreate, CuentaUsuarioOut, SuscriptorProfileOut, SuscriptorUpdateRequest,
    Token, UserProfileOut, TokenData, RefreshTokenRequest, LogoutRequest
)

from uuid import UUID

from app.services.email_service import enviar_email_recuperacion_contrasena, enviar_email_verificacion
from app.services.s3_service import is_s3_configured, upload_file_to_s3
import secrets, jwt
import logging
from typing import List

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post(
    "/register/administrador",
    response_model=AdminOut,
    status_code=status.HTTP_201_CREATED
)
def register_admin(
    payload: AdminCreate,
    db: Session = Depends(get_db)
):
    if db.query(Administrador).filter_by(email=payload.email).first():
        raise HTTPException(status_code=400, detail="El email ya estÃƒÂ¡ registrado")
    rol_admin = db.query(Rol).filter_by(nombre="admin").first()
    if not rol_admin:
        raise HTTPException(status_code=500, detail="Rol 'admin' no configurado")
    hashed = hash_password(payload.password)
    admin = Administrador(
        email=payload.email,
        password_hash=hashed,
        rol_id=rol_admin.id
    )
    db.add(admin)
    db.commit()
    db.refresh(admin)
    return admin


@router.post(
    "/register/suscriptor",
    response_model=SuscriptorOut,
    status_code=status.HTTP_201_CREATED
)
def register_suscriptor(
    payload: SuscriptorCreate,
    db: Session = Depends(get_db)
):
    if db.query(Suscriptor).filter_by(email=payload.email).first():
        raise HTTPException(status_code=400, detail="El email ya estÃƒÂ¡ registrado")
    rol_empresa = db.query(Rol).filter_by(nombre="empresa").first()
    if not rol_empresa:
        raise HTTPException(status_code=500, detail="Rol 'empresa' no configurado")
    hashed = hash_password(payload.password)
    sus = Suscriptor(
        nombre=payload.nombre,
        email=payload.email,
        telefono=payload.telefono,
        password_hash=hashed,
        rol_id=rol_empresa.id
    )
    db.add(sus)
    db.commit()
    db.refresh(sus)
    return sus


@router.post(
    "/register/usuario",
    response_model=CuentaUsuarioOut,
    status_code=status.HTTP_201_CREATED
)
async def register_usuario(
    payload: CuentaUsuarioCreate,
    db: Session = Depends(get_db)
):
    exists = db.query(CuentaUsuario).filter_by(
        suscriptor_id=payload.suscriptor_id,
        email=payload.email
    ).first()
    if exists:
        raise HTTPException(status_code=400, detail="El email ya está registrado para este suscriptor")

    from app.services.plan_limits_service import validate_operadores_limit
    validate_operadores_limit(db, payload.suscriptor_id)

    rol_operator = db.query(Rol).filter_by(nombre="operator").first()
    if not rol_operator:
        raise HTTPException(status_code=500, detail="Rol 'operator' no configurado")

    hashed = hash_password(payload.password)
    user = CuentaUsuario(
        suscriptor_id=payload.suscriptor_id,
        nombre_completo=payload.nombre_completo,
        email=payload.email,
        password_hash=hashed,
        rol_id=rol_operator.id
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    #  Enviar correo para que cambie la contraseña
    reset_token = secrets.token_urlsafe(32)
    token_data = {
        "sub": payload.email,
        "reset_token": reset_token,
        "exp": datetime.utcnow() + timedelta(hours=1)
    }
    token = jwt.encode(token_data, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    reset_link = f"{settings.clean_frontend_url}/reset-password?token={token}"

    try:
        enviado = await enviar_email_recuperacion_contrasena(
            destinatario_email=payload.email,
            destinatario_nombre=payload.nombre_completo,
            url_reset=reset_link
        )
        if not enviado:
            logger.warning("No se pudo enviar el correo de recuperación a %s (SMTP deshabilitado o no configurado)", payload.email)
    except Exception as e:
        logger.error("Error enviando correo de recuperación a %s: %s", payload.email, e)

    return user


@router.post("/login", response_model=Token)
def login(
    credentials: LoginRequest,
    db: Session = Depends(get_db)
):
    email = credentials.email
    password = credentials.password

    user = db.query(Administrador).filter_by(email=email).first()
    if not user:
        user = db.query(Suscriptor).filter_by(email=email).first()
    if not user:
        user = db.query(CuentaUsuario).filter_by(email=email).first()

    if not user or not verify_password(password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales inválidas"
        )

    # Validar estado de la empresa/suscriptor antes de autorizar login
    if isinstance(user, Suscriptor):
        estado_sus = getattr(user, "estado", "") or ""
        if estado_sus.strip().lower() in ["pendiente", "inactivo"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Debes verificar tu correo electrónico antes de ingresar. Revisa el correo de bienvenida que te enviamos."
            )

    # Validar si el operador/cuenta de usuario está activa
    if isinstance(user, CuentaUsuario) and not getattr(user, "activo", True):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tu cuenta de usuario se encuentra inactiva. Contacta al administrador."
        )

    # obtengo el nombre del rol y permisos para el token
    rol = db.get(Rol, user.rol_id)
    permisos_list = [p.codigo for p in rol.permisos] if rol and rol.permisos else []
    
    access_token = create_access_token(
        subject=str(user.id),
        role=rol.nombre if rol else "usuario",
        permisos=permisos_list
    )
    refresh_token = create_refresh_token(db, user.id)

    # Registrar evento de inicio de sesión en bitácora
    try:
        from app.services.audit_service import registrar_auditoria
        sus_id = getattr(user, "suscriptor_id", None) or (user.id if isinstance(user, Suscriptor) else None)
        registrar_auditoria(
            db=db,
            accion="LOGIN",
            modulo="AUTH",
            usuario_id=user.id,
            usuario_email=user.email,
            rol=rol.nombre if rol else "usuario",
            suscriptor_id=sus_id,
            detalles={"tipo_usuario": user.__class__.__name__}
        )
    except Exception as e_audit:
        logger.warning("No se pudo registrar auditoría de login: %s", e_audit)

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    }


@router.post("/refresh", response_model=Token)
def refresh_access_token(
    payload: RefreshTokenRequest,
    db: Session = Depends(get_db)
):
    """
    Renueva el access_token y rota el refresh_token de forma segura.
    Si el refresh_token fue revocado o expiró, retorna 401.
    """
    db_token, nuevo_refresh_token = rotate_refresh_token(db, payload.refresh_token)

    # Identificar el usuario
    user = db.query(Administrador).filter_by(id=db_token.user_id).first()
    if not user:
        user = db.query(Suscriptor).filter_by(id=db_token.user_id).first()
    if not user:
        user = db.query(CuentaUsuario).filter_by(id=db_token.user_id).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuario asociado al token no encontrado"
        )

    rol = db.get(Rol, user.rol_id)
    permisos_list = [p.codigo for p in rol.permisos] if rol and rol.permisos else []

    nuevo_access_token = create_access_token(
        subject=str(user.id),
        role=rol.nombre if rol else "usuario",
        permisos=permisos_list
    )

    return {
        "access_token": nuevo_access_token,
        "refresh_token": nuevo_refresh_token,
        "token_type": "bearer",
        "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    }


@router.post("/logout", status_code=status.HTTP_200_OK)
def logout(
    payload: LogoutRequest,
    db: Session = Depends(get_db)
):
    """
    Revoca activamente el refresh_token en el servidor, garantizando que
    no pueda ser utilizado para renovar sesiones (logout real).
    """
    revocado = revoke_refresh_token(db, payload.refresh_token)
    return {
        "mensaje": "Sesión cerrada y refresh token revocado con éxito" if revocado else "Refresh token no encontrado o ya revocado",
        "revocado": revocado
    }


@router.get("/me", response_model=UserProfileOut)
def get_current_user_profile(
    token_data: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Obtener el ID del usuario desde el token
    user_id = token_data.sub
    role = token_data.role
    
    if role == "admin":
        user = db.query(Administrador).filter(Administrador.id == UUID(user_id)).first()
        if not user:
            raise HTTPException(status_code=404, detail="Administrador no encontrado")
        rol = db.get(Rol, user.rol_id)
        permisos_list = [p.codigo for p in rol.permisos] if rol and rol.permisos else []
        return AdminProfileOut(
            id=user.id,
            email=user.email,
            rol=rol.nombre if rol else "admin",
            permisos=permisos_list,
            activo=user.activo,
            creado_en=user.creado_en,
            foto_url=user.foto_url
        )
        
    elif role == "empresa":
        user = db.query(Suscriptor).filter(Suscriptor.id == UUID(user_id)).first()
        if not user:
            raise HTTPException(status_code=404, detail="Suscriptor no encontrado")
        rol = db.get(Rol, user.rol_id)
        permisos_list = [p.codigo for p in rol.permisos] if rol and rol.permisos else []
        return SuscriptorProfileOut(
            id=user.id,
            email=user.email,
            rol=rol.nombre if rol else "empresa",
            permisos=permisos_list,
            nombre=user.nombre,
            telefono=user.telefono,
            estado=user.estado,
            creado_en=user.creado_en,
            foto_url=user.foto_url
        )
        
    elif role in ["operator", "analista"]:
        user = db.query(CuentaUsuario).filter(CuentaUsuario.id == UUID(user_id)).first()
        if not user:
            raise HTTPException(status_code=404, detail="Usuario no encontrado")
        rol = db.get(Rol, user.rol_id)
        permisos_list = [p.codigo for p in rol.permisos] if rol and rol.permisos else []
        return OperatorProfileOut(
            id=user.id,
            email=user.email,
            rol=rol.nombre if rol else role,
            permisos=permisos_list,
            nombre_completo=user.nombre_completo,
            suscriptor_id=user.suscriptor_id,
            activo=user.activo,
            creado_en=user.creado_en,
            foto_url=user.foto_url
        )
    
    raise HTTPException(status_code=400, detail="Tipo de usuario no reconocido")


@router.post("/perfil/foto", summary="Subir o actualizar foto de perfil del usuario autenticado")
async def upload_foto_perfil(
    file: UploadFile = File(...),
    token_data: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="El archivo subido debe ser una imagen (JPG, PNG, WEBP, GIF)")

    from uuid import uuid4

    ext = file.filename.split(".")[-1] if (file.filename and "." in file.filename) else "jpg"
    s3_key = f"avatars/{token_data.sub}_{uuid4().hex[:8]}.{ext}"

    if is_s3_configured():
        foto_url = await upload_file_to_s3(file, s3_key)
    else:
        # Fallback local para desarrollo o entornos de test sin credenciales de S3
        import os
        os.makedirs(os.path.join("uploads", "avatars"), exist_ok=True)
        filename = f"avatar_{token_data.sub}_{uuid4().hex[:8]}.{ext}"
        file_path = os.path.join("uploads", "avatars", filename)
        file.file.seek(0)
        contents = await file.read()
        with open(file_path, "wb") as f:
            f.write(contents)
        foto_url = f"/uploads/avatars/{filename}"

    role = token_data.role
    user_id = UUID(token_data.sub)

    if role == "admin":
        user = db.get(Administrador, user_id)
    elif role == "empresa":
        user = db.get(Suscriptor, user_id)
    else:
        user = db.get(CuentaUsuario, user_id)

    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    user.foto_url = foto_url
    db.commit()

    return {
        "mensaje": "Foto de perfil actualizada exitosamente",
        "message": "Foto de perfil actualizada exitosamente",
        "foto_url": foto_url
    }


@router.post(
    "/request-registration",
    status_code=status.HTTP_200_OK
)
async def request_registration(
    payload: SuscriptorCreate,
    db: Session = Depends(get_db)
):
    from uuid import uuid4
    from datetime import datetime, timezone, timedelta
    import jwt
    from app.core.security import hash_password

    # 1. Verifica que no haya un admin o cuenta_usuario con ese email
    if db.query(Administrador).filter_by(email=payload.email).first():
        raise HTTPException(status_code=400, detail="El email ya está registrado")
    if db.query(CuentaUsuario).filter_by(email=payload.email).first():
        raise HTTPException(status_code=400, detail="El email ya está registrado")

    # 2. Verifica si la empresa ya existe en BD
    password_hash = hash_password(payload.password)
    sus_existente = db.query(Suscriptor).filter_by(email=payload.email).first()

    if sus_existente:
        if sus_existente.estado and sus_existente.estado.lower() == "activo":
            raise HTTPException(status_code=400, detail="El email ya está registrado")
        # Si estaba en estado pendiente/inactivo, actualizamos datos y regeneramos credenciales
        sus = sus_existente
        sus.nombre = payload.nombre
        sus.telefono = payload.telefono
        sus.password_hash = password_hash
        sus.estado = "pendiente"
        db.commit()
        db.refresh(sus)
    else:
        rol_empresa = db.query(Rol).filter_by(nombre="empresa").first()
        sus = Suscriptor(
            id=uuid4(),
            nombre=payload.nombre,
            email=payload.email,
            telefono=payload.telefono,
            password_hash=password_hash,
            rol_id=rol_empresa.id if rol_empresa else 1,
            estado="pendiente"
        )
        db.add(sus)
        db.commit()
        db.refresh(sus)

    # 3. Generar el token (JWT) de verificación por correo
    token_data = {
        "sub": payload.email,
        "nombre": payload.nombre,
        "telefono": payload.telefono,
        "suscriptor_id": str(sus.id),
        "exp": datetime.now(timezone.utc) + timedelta(hours=24)
    }

    token = jwt.encode(
        token_data,
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM
    )

    # 4. Armar los links oficiales para la Landing Page y correos
    url_verificacion = f"{settings.clean_frontend_url}/verificar-registro?token={token}"
    url_terminos = f"{settings.clean_frontend_url}/terminos"
    url_privacidad = f"{settings.clean_frontend_url}/privacidad"
    url_software = f"{settings.clean_frontend_url}/login"

    # 5. Enviar los 3 correos de validación, términos y bienvenida
    from app.services.email_service import (
        enviar_email_terminos,
        enviar_email_privacidad,
        enviar_email_bienvenida,
    )

    import asyncio
    try:
        await asyncio.gather(
            enviar_email_terminos(payload.email, payload.nombre, url_terminos),
            enviar_email_privacidad(payload.email, payload.nombre, url_privacidad),
            enviar_email_bienvenida(payload.email, payload.nombre, url_verificacion, url_software),
            return_exceptions=True
        )
    except Exception as e:
        logger.error(f"Error despachando correos de registro: {e}")

    return {
        "message": "Se han enviado 3 correos de verificación y bienvenida. Revisa tu bandeja de entrada."
    }


@router.get("/verify-registration")
@router.get("/verificar-registro")
@router.post("/verify-registration")
@router.post("/verificar-registro")
def verify_registration(
    token: str = Query(..., description="Token JWT de verificación de registro"),
    db: Session = Depends(get_db)
):
    import jwt
    from jwt import ExpiredSignatureError, InvalidTokenError
    from uuid import uuid4
    from app.core.security import create_access_token

    try:
        # Decodificar el token
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM]
        )

        email = payload.get("sub")
        nombre = payload.get("nombre", "")
        telefono = payload.get("telefono")

        # Buscar el rol de empresa
        rol_empresa = db.query(Rol).filter_by(nombre="empresa").first()
        if not rol_empresa:
            rol_empresa = db.get(Rol, 1)
        if not rol_empresa:
            rol_empresa = Rol(id=1, nombre="empresa")
            db.add(rol_empresa)
            db.commit()

        # Buscar suscriptor por email
        sus = db.query(Suscriptor).filter_by(email=email).first()
        if sus:
            sus.estado = "activo"
        else:
            sus = Suscriptor(
                id=uuid4(),
                nombre=nombre,
                email=email,
                telefono=telefono,
                password_hash=payload.get("password_hash", ""),
                rol_id=rol_empresa.id if rol_empresa else 1,
                estado="activo"
            )
            db.add(sus)

        db.commit()
        db.refresh(sus)

        # Generar access_token y refresh_token
        role_name = rol_empresa.nombre if rol_empresa else "empresa"
        access_token = create_access_token(subject=str(sus.id), role=role_name)
        refresh_token = create_refresh_token(db, sus.id)

        return {
            "message": "Cuenta activada correctamente",
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "estado": "activo"
        }

    except ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="El enlace ha expirado")
    except InvalidTokenError:
        raise HTTPException(status_code=401, detail="Token inválido")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al activar la cuenta: {str(e)}")


@router.post("/forgot-password")
async def forgot_password(
    payload: ForgotPasswordRequest,
    db: Session = Depends(get_db)
):
    email = payload.email

    user = (
        db.query(Administrador).filter_by(email=email).first()
        or db.query(Suscriptor).filter_by(email=email).first()
        or db.query(CuentaUsuario).filter_by(email=email).first()
    )
    if not user:
        return {"message": "Si el correo está registrado, se enviará un enlace para restablecer la contraseña."}

    reset_token = secrets.token_urlsafe(32)
    token_data = {
        "sub": email,
        "reset_token": reset_token,
        "exp": datetime.utcnow() + timedelta(hours=1)
    }
    token = jwt.encode(token_data, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    reset_link = f"{settings.clean_frontend_url}/reset-password?token={token}"

    enviado = await enviar_email_recuperacion_contrasena(
        destinatario_email=email,
        destinatario_nombre=getattr(user, "nombre", getattr(user, "nombre_completo", "")),
        url_reset=reset_link
    )

    if not enviado:
        raise HTTPException(status_code=500, detail="No se pudo enviar el correo de recuperación")

    return {"message": "Correo enviado correctamente"}

@router.post("/reset-password")
def reset_password(
    payload: ResetPasswordRequest,
    db: Session = Depends(get_db)
):
    try:
        decoded = jwt.decode(payload.token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        email = decoded["sub"]

        user = (
            db.query(Administrador).filter_by(email=email).first()
            or db.query(Suscriptor).filter_by(email=email).first()
            or db.query(CuentaUsuario).filter_by(email=email).first()
        )
        if not user:
            raise HTTPException(status_code=404, detail="Usuario no encontrado")

        user.password_hash = hash_password(payload.new_password)
        db.commit()

        return {"message": "Contraseña actualizada correctamente"}

    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=400, detail="El token ha expirado")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=400, detail="Token inválido")

@router.put("/update/admin", response_model=AdminProfileOut)
def update_admin_profile(
    payload: AdminUpdateRequest,
    token_data: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if token_data.role != "admin":
        raise HTTPException(status_code=403, detail="Acceso no autorizado")

    admin = db.query(Administrador).filter_by(id=token_data.sub).first()
    if not admin:
        raise HTTPException(status_code=404, detail="Administrador no encontrado")

    admin.email = payload.email
    db.commit()
    db.refresh(admin)

    rol = db.get(Rol, admin.rol_id)
    return AdminProfileOut(
        id=admin.id,
        email=admin.email,
        rol=rol.nombre,
        activo=admin.activo,
        creado_en=admin.creado_en
    )


@router.put("/update/suscriptor", response_model=SuscriptorProfileOut)
def update_suscriptor_profile(
    payload: SuscriptorUpdateRequest,
    token_data: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if token_data.role != "empresa":
        raise HTTPException(status_code=403, detail="Acceso no autorizado")

    suscriptor = db.query(Suscriptor).filter_by(id=token_data.sub).first()
    if not suscriptor:
        raise HTTPException(status_code=404, detail="Suscriptor no encontrado")

    suscriptor.nombre = payload.nombre
    suscriptor.email = payload.email
    suscriptor.telefono = payload.telefono
    db.commit()
    db.refresh(suscriptor)

    rol = db.get(Rol, suscriptor.rol_id)
    return SuscriptorProfileOut(
        id=suscriptor.id,
        nombre=suscriptor.nombre,
        email=suscriptor.email,
        telefono=suscriptor.telefono,
        estado=suscriptor.estado,
        rol=rol.nombre,
        creado_en=suscriptor.creado_en
    )


@router.put("/update/operator", response_model=OperatorProfileOut)
def update_operator_profile(
    payload: OperatorUpdateRequest,
    token_data: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if token_data.role != "operator":
        raise HTTPException(status_code=403, detail="Acceso no autorizado")

    user = db.query(CuentaUsuario).filter_by(id=token_data.sub).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    if payload.email != user.email:
        exists = db.query(CuentaUsuario).filter(
            CuentaUsuario.suscriptor_id == user.suscriptor_id,
            CuentaUsuario.email == payload.email,
            CuentaUsuario.id != user.id
        ).first()
        if exists:
            raise HTTPException(status_code=400, detail="El email ya está registrado para este suscriptor")

    user.nombre_completo = payload.nombre_completo
    user.email = payload.email
    db.commit()
    db.refresh(user)

    rol = db.get(Rol, user.rol_id)
    return OperatorProfileOut(
        id=user.id,
        email=user.email,
        rol=rol.nombre,
        nombre_completo=user.nombre_completo,
        suscriptor_id=user.suscriptor_id,
        activo=user.activo,
        creado_en=user.creado_en
    )

@router.get(
    "/operadores/{suscriptor_id}",
    response_model=List[OperatorProfileOut],
    status_code=status.HTTP_200_OK
)
def listar_operadores_de_suscriptor(
    suscriptor_id: UUID,
    db: Session = Depends(get_db),
    token_data: TokenData = Depends(get_current_user),
):
    # Solo el propio suscriptor o un admin puede ver los operadores
    if token_data.role not in ("empresa", "admin"):
        raise HTTPException(status_code=403, detail="No autorizado")
    if token_data.role == "empresa" and token_data.sub != str(suscriptor_id):
        raise HTTPException(status_code=403, detail="No puedes ver operadores de otro suscriptor")

    operadores = db.query(CuentaUsuario).filter_by(suscriptor_id=suscriptor_id).all()

    return [
        OperatorProfileOut(
            id=o.id,
            email=o.email,
            rol=db.get(Rol, o.rol_id).nombre,
            nombre_completo=o.nombre_completo,
            suscriptor_id=o.suscriptor_id,
            activo=o.activo,
            creado_en=o.creado_en
        )
        for o in operadores
    ]
