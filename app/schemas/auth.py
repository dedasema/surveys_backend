from pydantic import BaseModel, EmailStr
from typing import Optional, Union, List
from datetime import datetime
from uuid import UUID

class AdminCreate(BaseModel):
    email: EmailStr
    password: str

class AdminOut(BaseModel):
    id: UUID
    email: EmailStr
    activo: bool
    rol_id: int
    creado_en: datetime
    model_config = {"from_attributes": True}


class SuscriptorCreate(BaseModel):
    nombre: str
    email: EmailStr
    telefono: Optional[str] = None
    password: str

class SuscriptorOut(BaseModel):
    id: UUID
    nombre: str
    email: EmailStr
    telefono: Optional[str]
    estado: str
    creado_en: datetime
    model_config = {"from_attributes": True}


class CuentaUsuarioCreate(BaseModel):
    suscriptor_id: UUID
    nombre_completo: str
    email: EmailStr
    password: str

class CuentaUsuarioOut(BaseModel):
    id: UUID
    suscriptor_id: UUID
    nombre_completo: str
    email: EmailStr
    activo: bool
    rol_id: int
    creado_en: datetime
    model_config = {"from_attributes": True}


class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = 1800

class TokenData(BaseModel):
    sub: Optional[str] = None
    role: Optional[str] = None
    permisos: List[str] = []

class RefreshTokenRequest(BaseModel):
    refresh_token: str

class LogoutRequest(BaseModel):
    refresh_token: str

class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserProfileBase(BaseModel):
    id: UUID
    email: str
    rol: str
    permisos: List[str] = []
    creado_en: datetime
    foto_url: Optional[str] = None
    
    model_config = {"from_attributes": True}

class AdminProfileOut(UserProfileBase):
    tipo: str = "admin"
    activo: bool

class SuscriptorProfileOut(UserProfileBase):
    tipo: str = "suscriptor"
    nombre: str
    telefono: str
    estado: Optional[str] = None

class OperatorProfileOut(UserProfileBase):
    tipo: str = "operator"
    nombre_completo: str
    suscriptor_id: UUID
    activo: bool

class ForgotPasswordRequest(BaseModel):
    email: EmailStr

class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str

class AdminUpdateRequest(BaseModel):
    email: EmailStr

class SuscriptorUpdateRequest(BaseModel):
    nombre: str
    email: EmailStr
    telefono: Optional[str] = None

class OperatorUpdateRequest(BaseModel):
    nombre_completo: str
    email: EmailStr
    
UserProfileOut = Union[AdminProfileOut, SuscriptorProfileOut, OperatorProfileOut]