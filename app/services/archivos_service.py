# app/services/archivos_service.py
import os
import uuid
import mimetypes
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Tuple
from uuid import UUID
from fastapi import UploadFile, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import or_

from app.models.archivo_empresa import ArchivoEmpresa
from app.models.audio_respuesta import AudioRespuesta
from app.models.survey import EntregaEncuesta, CampanaEncuesta
from app.models.suscriptor import Suscriptor
from app.models.cuenta_usuario import CuentaUsuario
from app.services.audit_service import registrar_auditoria

def format_file_size(size_bytes: int) -> Tuple[float, str, str]:
    """
    Convierte bytes a un valor escalado, unidad y texto legible.
    """
    if size_bytes < 1024:
        return float(size_bytes), "Bytes", f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        val = round(size_bytes / 1024.0, 2)
        return val, "KB", f"{val} KB"
    else:
        val = round(size_bytes / (1024.0 * 1024.0), 2)
        return val, "MB", f"{val} MB"

def get_mime_type(filename: str, fallback: str = "application/octet-stream") -> str:
    mime, _ = mimetypes.guess_type(filename)
    if mime:
        return mime
    ext = os.path.splitext(filename)[1].lower()
    mapping = {
        ".mp3": "audio/mpeg",
        ".wav": "audio/wav",
        ".m4a": "audio/mp4",
        ".ogg": "audio/ogg",
        ".pdf": "application/pdf",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".csv": "text/csv",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    }
    return mapping.get(ext, fallback)

def _get_physical_file_size(relative_url: str) -> int:
    """Calcula el tamaño real en disco si existe; si no, devuelve un fallback heurístico."""
    if not relative_url:
        return 0
    clean_path = relative_url.lstrip("/")
    if os.path.exists(clean_path):
        return os.path.getsize(clean_path)
    return 1024  # Fallback a 1KB si es mock o no existe físicamente

def listar_archivos_empresa(
    db: Session,
    suscriptor_id: UUID,
    categoria: Optional[str] = None,
    busqueda: Optional[str] = None,
    limit: int = 20,
    offset: int = 0
) -> Tuple[int, List[Dict[str, Any]], float]:
    """
    Consolida todos los archivos asociados a la empresa:
    1. Archivos directos del tenant (ArchivoEmpresa)
    2. Audios de respuestas de campañas (AudioRespuesta)
    3. Avatares del suscriptor y sus operadores
    """
    archivos_consolidados: List[Dict[str, Any]] = []

    # 1. Archivos directos de la empresa
    q_archivos = db.query(ArchivoEmpresa).filter(ArchivoEmpresa.suscriptor_id == suscriptor_id)
    for a in q_archivos.all():
        peso_val, unidad, _ = format_file_size(a.peso_bytes)
        archivos_consolidados.append({
            "id": str(a.id),
            "archivo": a.nombre,
            "extension": a.extension,
            "peso": peso_val,
            "unidad": unidad,
            "peso_bytes": a.peso_bytes,
            "url_descarga": a.ruta,
            "opcion_ver_descargar": {
                "ver": a.mime_type.startswith(("image/", "audio/", "application/pdf")),
                "descargar": True,
                "url": a.ruta
            },
            "mime_type": a.mime_type,
            "categoria": a.categoria,
            "contexto": a.contexto or "Documento del Sistema",
            "fecha_subida": a.creado_en.isoformat() if a.creado_en else datetime.now(timezone.utc).isoformat(),
            "creado_por": a.creado_por
        })

    # 2. Audios de respuestas de encuestas de la empresa
    audios = (
        db.query(AudioRespuesta, CampanaEncuesta.nombre)
        .join(EntregaEncuesta, AudioRespuesta.entrega_id == EntregaEncuesta.id)
        .join(CampanaEncuesta, EntregaEncuesta.campana_id == CampanaEncuesta.id)
        .filter(CampanaEncuesta.suscriptor_id == suscriptor_id)
        .all()
    )
    for audio, campana_nombre in audios:
        nombre_archivo = os.path.basename(audio.archivo_url) if audio.archivo_url else f"audio_{audio.id}.{audio.formato}"
        ext = f".{audio.formato}" if not audio.formato.startswith(".") else audio.formato
        size_bytes = _get_physical_file_size(audio.archivo_url)
        peso_val, unidad, _ = format_file_size(size_bytes)
        mime = get_mime_type(nombre_archivo, fallback=f"audio/{audio.formato}")

        archivos_consolidados.append({
            "id": str(audio.id),
            "archivo": nombre_archivo,
            "extension": ext,
            "peso": peso_val,
            "unidad": unidad,
            "peso_bytes": size_bytes,
            "url_descarga": audio.archivo_url,
            "opcion_ver_descargar": {
                "ver": True,
                "descargar": True,
                "url": audio.archivo_url
            },
            "mime_type": mime,
            "categoria": "audio_respuesta",
            "contexto": f"Campaña: {campana_nombre}",
            "fecha_subida": audio.creado_en.isoformat() if audio.creado_en else datetime.now(timezone.utc).isoformat(),
            "creado_por": "Respondente de Encuesta"
        })

    # 3. Avatares de la empresa y operadores
    sus = db.query(Suscriptor).filter(Suscriptor.id == suscriptor_id).first()
    if sus and sus.foto_url:
        nombre_avatar = os.path.basename(sus.foto_url)
        ext = os.path.splitext(nombre_avatar)[1] or ".png"
        size_bytes = _get_physical_file_size(sus.foto_url)
        peso_val, unidad, _ = format_file_size(size_bytes)
        archivos_consolidados.append({
            "id": f"avatar-sus-{sus.id}",
            "archivo": nombre_avatar,
            "extension": ext,
            "peso": peso_val,
            "unidad": unidad,
            "peso_bytes": size_bytes,
            "url_descarga": sus.foto_url,
            "opcion_ver_descargar": {
                "ver": True,
                "descargar": True,
                "url": sus.foto_url
            },
            "mime_type": get_mime_type(nombre_avatar, "image/png"),
            "categoria": "avatar",
            "contexto": "Logotipo / Avatar de Empresa",
            "fecha_subida": sus.creado_en.isoformat() if sus.creado_en else datetime.now(timezone.utc).isoformat(),
            "creado_por": sus.email
        })

    cuentas = db.query(CuentaUsuario).filter(CuentaUsuario.suscriptor_id == suscriptor_id).all()
    for c in cuentas:
        if c.foto_url:
            nombre_avatar = os.path.basename(c.foto_url)
            ext = os.path.splitext(nombre_avatar)[1] or ".png"
            size_bytes = _get_physical_file_size(c.foto_url)
            peso_val, unidad, _ = format_file_size(size_bytes)
            archivos_consolidados.append({
                "id": f"avatar-usr-{c.id}",
                "archivo": nombre_avatar,
                "extension": ext,
                "peso": peso_val,
                "unidad": unidad,
                "peso_bytes": size_bytes,
                "url_descarga": c.foto_url,
                "opcion_ver_descargar": {
                    "ver": True,
                    "descargar": True,
                    "url": c.foto_url
                },
                "mime_type": get_mime_type(nombre_avatar, "image/png"),
                "categoria": "avatar",
                "contexto": f"Avatar de {c.nombre_completo}",
                "fecha_subida": c.creado_en.isoformat() if c.creado_en else datetime.now(timezone.utc).isoformat(),
                "creado_por": c.email
            })

    # Filtros
    if categoria:
        cat_lower = categoria.strip().lower()
        archivos_consolidados = [a for a in archivos_consolidados if a["categoria"].lower() == cat_lower]

    if busqueda:
        term = busqueda.strip().lower()
        archivos_consolidados = [
            a for a in archivos_consolidados
            if term in a["archivo"].lower() or (a["contexto"] and term in a["contexto"].lower()) or term in a["extension"].lower()
        ]

    # Ordenar por fecha_subida descendente
    archivos_consolidados.sort(key=lambda x: x["fecha_subida"], reverse=True)

    total = len(archivos_consolidados)
    total_bytes = sum(a["peso_bytes"] for a in archivos_consolidados)
    espacio_mb = round(total_bytes / (1024.0 * 1024.0), 2)

    paginated = archivos_consolidados[offset : offset + limit]
    return total, paginated, espacio_mb

async def subir_archivo_empresa(
    db: Session,
    suscriptor_id: UUID,
    file: UploadFile,
    categoria: str = "documento",
    contexto: Optional[str] = None,
    usuario_email: Optional[str] = None
) -> Dict[str, Any]:
    """
    Almacena físicamente un archivo en uploads/archivos/{suscriptor_id}/ y registra en BD y Bitácora.
    """
    original_name = file.filename or "archivo_sin_nombre"
    ext = os.path.splitext(original_name)[1].lower() or ".bin"
    file_id = uuid.uuid4()
    saved_filename = f"{file_id}{ext}"

    dir_path = os.path.join("uploads", "archivos", str(suscriptor_id))
    os.makedirs(dir_path, exist_ok=True)
    full_path = os.path.join(dir_path, saved_filename)

    content = await file.read()
    size_bytes = len(content)

    with open(full_path, "wb") as f:
        f.write(content)

    relative_url = f"/uploads/archivos/{suscriptor_id}/{saved_filename}".replace("\\", "/")
    mime = file.content_type or get_mime_type(original_name)

    nuevo_archivo = ArchivoEmpresa(
        id=file_id,
        suscriptor_id=suscriptor_id,
        nombre=original_name,
        nombre_guardado=saved_filename,
        ruta=relative_url,
        extension=ext,
        peso_bytes=size_bytes,
        mime_type=mime,
        categoria=categoria,
        contexto=contexto,
        creado_por=usuario_email
    )
    db.add(nuevo_archivo)
    db.commit()
    db.refresh(nuevo_archivo)

    # Registro en bitácora
    registrar_auditoria(
        db=db,
        accion="CREAR",
        modulo="ARCHIVOS",
        suscriptor_id=suscriptor_id,
        usuario_email=usuario_email,
        entidad_id=str(nuevo_archivo.id),
        detalles={"archivo": original_name, "peso_bytes": size_bytes, "categoria": categoria}
    )

    peso_val, unidad, _ = format_file_size(size_bytes)
    return {
        "id": str(nuevo_archivo.id),
        "archivo": nuevo_archivo.nombre,
        "extension": nuevo_archivo.extension,
        "peso": peso_val,
        "unidad": unidad,
        "peso_bytes": nuevo_archivo.peso_bytes,
        "url_descarga": nuevo_archivo.ruta,
        "opcion_ver_descargar": {
            "ver": mime.startswith(("image/", "audio/", "application/pdf")),
            "descargar": True,
            "url": nuevo_archivo.ruta
        },
        "mime_type": nuevo_archivo.mime_type,
        "categoria": nuevo_archivo.categoria,
        "contexto": nuevo_archivo.contexto,
        "fecha_subida": nuevo_archivo.creado_en.isoformat(),
        "creado_por": nuevo_archivo.creado_por
    }

def eliminar_archivo_empresa(
    db: Session,
    suscriptor_id: UUID,
    archivo_id: UUID,
    usuario_email: Optional[str] = None
) -> bool:
    """Elimina físicamente y de la BD un archivo del tenant."""
    archivo = db.query(ArchivoEmpresa).filter(
        ArchivoEmpresa.id == archivo_id,
        ArchivoEmpresa.suscriptor_id == suscriptor_id
    ).first()

    if not archivo:
        return False

    clean_path = archivo.ruta.lstrip("/")
    if os.path.exists(clean_path):
        try:
            os.remove(clean_path)
        except Exception as e:
            print(f"Error borrando archivo en disco: {e}")

    db.delete(archivo)
    db.commit()

    registrar_auditoria(
        db=db,
        accion="ELIMINAR",
        modulo="ARCHIVOS",
        suscriptor_id=suscriptor_id,
        usuario_email=usuario_email,
        entidad_id=str(archivo_id),
        detalles={"archivo": archivo.nombre}
    )
    return True
