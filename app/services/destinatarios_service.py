import io
import csv
from typing import List, Optional, Dict

try:
    import openpyxl
except Exception:
    openpyxl = None  # type: ignore

try:
    import pandas as pd
except Exception:
    pd = None  # type: ignore

from fastapi import UploadFile, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import or_
from uuid import UUID

from app.models.survey import Destinatario
from app.schemas.destinatarios_schema import DestinarioCreate, DestinarioUpdate

def create_destinatario(
    db: Session, 
    suscriptor_id: UUID, 
    payload: DestinarioCreate
) -> Destinatario:
    destinatario = Destinatario(**payload.model_dump(), suscriptor_id=suscriptor_id)
    db.add(destinatario)
    db.commit()
    db.refresh(destinatario)
    return destinatario

def get_destinatario(db: Session, destinatario_id: UUID) -> Optional[Destinatario]:
    return db.query(Destinatario).filter(Destinatario.id == destinatario_id).first()

def list_destinatarios(
    db: Session, 
    suscriptor_id: UUID,
    skip: int = 0,
    limit: int = 100
) -> List[Destinatario]:
    return (
        db.query(Destinatario)
        .filter(Destinatario.suscriptor_id == suscriptor_id)
        .offset(skip)
        .limit(limit)
        .all()
    )

def update_destinatario(
    db: Session, 
    destinatario_id: UUID, 
    payload: DestinarioUpdate
) -> Optional[Destinatario]:
    destinatario = get_destinatario(db, destinatario_id)
    if not destinatario:
        return None
    
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(destinatario, field, value)
    
    db.commit()
    db.refresh(destinatario)
    return destinatario

def delete_destinatario(db: Session, destinatario_id: UUID) -> bool:
    destinatario = get_destinatario(db, destinatario_id)
    if not destinatario:
        return False
    db.delete(destinatario)
    db.commit()
    return True

async def process_excel_destinatarios(
    db: Session,
    file: UploadFile,
    suscriptor_id: UUID
) -> Dict[str, int]:
    """
    Procesa un archivo Excel (.xlsx, .xls) o CSV (.csv) con destinatarios y los crea en la base de datos.
    Retorna estadísticas del proceso.
    """
    filename = file.filename.lower() if file.filename else ""
    if not (filename.endswith('.xlsx') or filename.endswith('.xls') or filename.endswith('.csv')):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El archivo debe ser un Excel (.xlsx, .xls) o CSV (.csv)"
        )

    try:
        contents = await file.read()
        rows: List[Dict[str, str]] = []

        # 1. Si es archivo CSV
        if filename.endswith('.csv'):
            try:
                text = contents.decode('utf-8-sig', errors='replace')
                reader = csv.DictReader(io.StringIO(text))
                for row in reader:
                    normalized = {str(k).strip().lower(): str(v).strip() for k, v in row.items() if k}
                    rows.append(normalized)
            except Exception as csv_err:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Error leyendo archivo CSV: {str(csv_err)}"
                )

        # 2. Si es Excel y openpyxl está disponible
        elif openpyxl is not None and (filename.endswith('.xlsx') or filename.endswith('.xls')):
            try:
                wb = openpyxl.load_workbook(filename=io.BytesIO(contents), data_only=True)
                sheet = wb.active
                headers = [str(cell.value).strip().lower() if cell.value is not None else "" for cell in sheet[1]]
                
                for row_cells in sheet.iter_rows(min_row=2, values_only=True):
                    if not any(row_cells):
                        continue
                    row_dict = {}
                    for idx, val in enumerate(row_cells):
                        if idx < len(headers) and headers[idx]:
                            row_dict[headers[idx]] = str(val).strip() if val is not None else ""
                    rows.append(row_dict)
            except Exception as openpyxl_err:
                if pd is not None:
                    try:
                        df = pd.read_excel(io.BytesIO(contents))
                        df.columns = [str(col).strip().lower() for col in df.columns]
                        rows = df.to_dict(orient='records')
                    except Exception as pd_err:
                        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Error leyendo Excel: {str(pd_err)}")
                else:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Error leyendo Excel con openpyxl: {str(openpyxl_err)}")

        # 3. Fallback a Pandas
        elif pd is not None:
            try:
                df = pd.read_excel(io.BytesIO(contents))
                df.columns = [str(col).strip().lower() for col in df.columns]
                rows = df.to_dict(orient='records')
            except Exception as pd_err:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Error procesando Excel: {str(pd_err)}")
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No se encontró una librería para leer Excel (openpyxl/pandas). Por favor sube un archivo CSV."
            )

        if not rows:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El archivo no contiene filas de datos válidas."
            )

        # Validar columnas (soporta nombre/name, email, telefono/phone)
        total = 0
        creados = 0
        duplicados = 0
        errores = 0

        for row in rows:
            total += 1
            try:
                nombre = str(row.get('nombre') or row.get('name') or '').strip()
                email = str(row.get('email') or '').strip() or None
                telefono = str(row.get('telefono') or row.get('phone') or '').strip() or None

                if not nombre and not email and not telefono:
                    continue
                if not nombre:
                    nombre = email or telefono or "Sin Nombre"

                # Verificar si ya existe por email o teléfono
                filters = []
                if email:
                    filters.append(Destinatario.email == email)
                if telefono:
                    filters.append(Destinatario.telefono == telefono)

                existing = None
                if filters:
                    existing = (
                        db.query(Destinatario)
                        .filter(
                            Destinatario.suscriptor_id == suscriptor_id,
                            or_(*filters)
                        )
                        .first()
                    )

                if existing:
                    duplicados += 1
                    continue

                destinatario = Destinatario(
                    suscriptor_id=suscriptor_id,
                    nombre=nombre,
                    email=email,
                    telefono=telefono
                )
                db.add(destinatario)
                creados += 1
            except Exception:
                errores += 1
                continue

        db.commit()

        return {
            "total_procesados": total,
            "creados": creados,
            "duplicados": duplicados,
            "errores": errores
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Error procesando el archivo: {str(e)}"
        )
    finally:
        try:
            file.file.close()
        except Exception:
            pass