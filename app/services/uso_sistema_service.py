# app/services/uso_sistema_service.py
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, List
from uuid import UUID
from sqlalchemy.orm import Session
from sqlalchemy import func, or_

from app.models.suscriptor import Suscriptor
from app.models.cuenta_usuario import CuentaUsuario
from app.models.subscription import SuscripcionSuscriptor, PagoSuscriptor, PlanSuscripcion
from app.models.audit_log import AuditLog
from app.models.refresh_token import RefreshToken
from app.services.archivos_service import listar_archivos_empresa

def obtener_uso_sistema_empresa(
    db: Session,
    suscriptor_id: UUID,
    dias: int = 30
) -> Dict[str, Any]:
    """
    Calcula de manera agregada y performante las métricas de uso del sistema para el suscriptor:
    - Última sesión
    - Espacio usado vs límite del plan
    - Pagos acumulados y frecuencia
    - Gráfica de días de mayor uso (últimos N días)
    - Top 5 usuarios más activos
    - Distribución CUD (Create, Update, Delete) de la bitácora
    """
    sus = db.query(Suscriptor).filter(Suscriptor.id == suscriptor_id).first()
    if not sus:
        raise ValueError(f"Suscriptor {suscriptor_id} no encontrado")

    # Mapeo de usuarios del tenant
    cuentas = db.query(CuentaUsuario).filter(CuentaUsuario.suscriptor_id == suscriptor_id).all()
    user_ids = [sus.id] + [c.id for c in cuentas]
    user_emails = [sus.email.lower()] + [c.email.lower() for c in cuentas]
    nombres_map = {sus.email.lower(): f"{sus.nombre} (Empresa)", str(sus.id): f"{sus.nombre} (Empresa)"}
    for c in cuentas:
        nombres_map[c.email.lower()] = c.nombre_completo
        nombres_map[str(c.id)] = c.nombre_completo

    fecha_limite = datetime.now(timezone.utc) - timedelta(days=dias)

    # 1. Última Sesión
    # Primero busca en AuditLog con acción 'LOGIN'
    log_login = (
        db.query(AuditLog)
        .filter(
            or_(
                AuditLog.suscriptor_id == suscriptor_id,
                AuditLog.usuario_id.in_(user_ids),
                func.lower(AuditLog.usuario_email).in_(user_emails)
            ),
            AuditLog.accion == "LOGIN"
        )
        .order_by(AuditLog.creado_en.desc())
        .first()
    )

    ultima_sesion_str = None
    if log_login and log_login.creado_en:
        ultima_sesion_str = log_login.creado_en.isoformat()
    else:
        # Fallback a refresh_token más reciente
        token_reciente = (
            db.query(RefreshToken)
            .filter(RefreshToken.user_id.in_(user_ids))
            .order_by(RefreshToken.creado_en.desc())
            .first()
        )
        if token_reciente and token_reciente.creado_en:
            ultima_sesion_str = token_reciente.creado_en.isoformat()
        elif sus.creado_en:
            ultima_sesion_str = sus.creado_en.isoformat()

    # 2. Espacio Usado
    _, _, espacio_mb = listar_archivos_empresa(db, suscriptor_id, limit=1, offset=0)
    espacio_bytes = int(espacio_mb * 1024 * 1024)

    # Buscar suscripción y cuota de almacenamiento
    suscripcion = (
        db.query(SuscripcionSuscriptor)
        .filter(
            SuscripcionSuscriptor.suscriptor_id == suscriptor_id,
            SuscripcionSuscriptor.estado == "activo"
        )
        .order_by(SuscripcionSuscriptor.inicia_en.desc())
        .first()
    )

    plan_nombre = "Gratuito"
    estado_sub = "activo"
    proximo_pago = None
    limite_mb = 100.0  # Plan Gratuito por defecto

    if suscripcion:
        estado_sub = suscripcion.estado
        if suscripcion.expira_en:
            proximo_pago = suscripcion.expira_en.isoformat()
        if suscripcion.plan:
            plan_nombre = suscripcion.plan.nombre
            if "profesional" in plan_nombre.lower():
                limite_mb = 1000.0
            elif "enterprise" in plan_nombre.lower():
                limite_mb = 10000.0
            else:
                limite_mb = 250.0

    porcentaje_usado = round((espacio_mb / limite_mb) * 100.0, 2) if limite_mb > 0 else 0.0

    espacio_detalle = {
        "bytes": espacio_bytes,
        "mb": espacio_mb,
        "limite_mb": limite_mb,
        "porcentaje_usado": min(porcentaje_usado, 100.0),
        "unidad": "MB",
        "formateado": f"{espacio_mb} MB de {limite_mb} MB"
    }

    # 3. Pagos acumulados
    total_pagos = (
        db.query(func.coalesce(func.sum(PagoSuscriptor.monto), 0.0))
        .filter(
            PagoSuscriptor.suscriptor_id == suscriptor_id,
            func.lower(PagoSuscriptor.estado) == "completado"
        )
        .scalar()
    )
    pago_acumulado = float(total_pagos or 0.0)

    # 4. Frecuencia de pago
    frecuencia_pago = "Mensual"

    # Base query para bitácora en la ventana de tiempo
    filtro_tenant_audit = or_(
        AuditLog.suscriptor_id == suscriptor_id,
        AuditLog.usuario_id.in_(user_ids),
        func.lower(AuditLog.usuario_email).in_(user_emails)
    )

    logs_ventana = (
        db.query(AuditLog)
        .filter(filtro_tenant_audit, AuditLog.creado_en >= fecha_limite)
        .all()
    )

    # Si no hay logs en los últimos N días, traer los más recientes para no dejar gráficas vacías
    if not logs_ventana:
        logs_ventana = (
            db.query(AuditLog)
            .filter(filtro_tenant_audit)
            .order_by(AuditLog.creado_en.desc())
            .limit(100)
            .all()
        )

    # 5. Gráfica de días de mayor uso
    dias_contador: Dict[str, int] = {}
    for log in logs_ventana:
        if log.creado_en:
            dia_key = log.creado_en.strftime("%Y-%m-%d")
            dias_contador[dia_key] = dias_contador.get(dia_key, 0) + 1

    grafica_dias = [
        {"fecha": fecha, "cantidad": cant}
        for fecha, cant in sorted(dias_contador.items(), key=lambda x: x[0])
    ]

    dia_pico = None
    if grafica_dias:
        pico = max(grafica_dias, key=lambda x: x["cantidad"])
        dia_pico = pico

    # 6. Top 5 usuarios con más actividad
    usuarios_actividad: Dict[str, Dict[str, Any]] = {}
    for log in logs_ventana:
        email = (log.usuario_email or "sistema@empresa.com").lower()
        uid = str(log.usuario_id) if log.usuario_id else None
        rol = log.rol or "operador"
        nombre = nombres_map.get(email, nombres_map.get(uid, email.split("@")[0].capitalize()))

        if email not in usuarios_actividad:
            usuarios_actividad[email] = {
                "usuario_id": uid,
                "email": email,
                "nombre": nombre,
                "rol": rol,
                "total_operaciones": 0
            }
        usuarios_actividad[email]["total_operaciones"] += 1

    top_5 = sorted(
        usuarios_actividad.values(),
        key=lambda x: x["total_operaciones"],
        reverse=True
    )[:5]

    # 7. Tipos de operaciones CUD (Create, Update, Delete)
    crear_acciones = {"CREAR", "REGISTRO", "INSERTAR", "PROGRAMAR"}
    modificar_acciones = {"MODIFICAR", "ACTUALIZAR", "EDITAR", "ASIGNAR_PERMISOS", "CAMBIAR_ESTADO"}
    eliminar_acciones = {"ELIMINAR", "BORRAR", "REVOCAR", "CANCELAR"}

    c_cnt, u_cnt, d_cnt, o_cnt = 0, 0, 0, 0
    for log in logs_ventana:
        acc = (log.accion or "").upper()
        if acc in crear_acciones:
            c_cnt += 1
        elif acc in modificar_acciones:
            u_cnt += 1
        elif acc in eliminar_acciones:
            d_cnt += 1
        else:
            o_cnt += 1

    total_ops = c_cnt + u_cnt + d_cnt + o_cnt
    pct_c = round((c_cnt / total_ops) * 100.0, 2) if total_ops > 0 else 0.0
    pct_u = round((u_cnt / total_ops) * 100.0, 2) if total_ops > 0 else 0.0
    pct_d = round((d_cnt / total_ops) * 100.0, 2) if total_ops > 0 else 0.0
    pct_o = round((o_cnt / total_ops) * 100.0, 2) if total_ops > 0 else 0.0

    operaciones_cud = {
        "crear": c_cnt,
        "modificar": u_cnt,
        "eliminar": d_cnt,
        "otros": o_cnt,
        "total": total_ops,
        "porcentajes": {
            "crear": pct_c,
            "modificar": pct_u,
            "eliminar": pct_d,
            "otros": pct_o
        }
    }

    return {
        "ultima_sesion": ultima_sesion_str,
        "espacio_usado": espacio_detalle,
        "pago_total_acumulado": pago_acumulado,
        "moneda": "usd",
        "frecuencia_pago": frecuencia_pago,
        "plan_nombre": plan_nombre,
        "estado_suscripcion": estado_sub,
        "proximo_pago": proximo_pago,
        "grafica_dias_mayor_uso": grafica_dias,
        "dia_pico": dia_pico,
        "top_5_usuarios": top_5,
        "tipos_operaciones_cud": operaciones_cud
    }
