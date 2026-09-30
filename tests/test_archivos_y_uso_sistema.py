import uuid
from datetime import datetime, timezone, timedelta
from io import BytesIO
from app.models.suscriptor import Suscriptor
from app.models.cuenta_usuario import CuentaUsuario
from app.models.subscription import PlanSuscripcion, SuscripcionSuscriptor, PagoSuscriptor
from app.models.audit_log import AuditLog
from app.models.archivo_empresa import ArchivoEmpresa
from app.models.audio_respuesta import AudioRespuesta
from app.models.survey import CampanaEncuesta, EntregaEncuesta, PlantillaEncuesta
from app.core.security import hash_password

def setup_test_empresa_data(db_session):
    empresa_id = uuid.UUID("00000000-0000-0000-0000-000000000002")
    
    # 1. Crear o recuperar suscriptor
    sus = db_session.query(Suscriptor).filter_by(id=empresa_id).first()
    if not sus:
        sus = Suscriptor(
            id=empresa_id,
            nombre="Empresa Demo Test",
            email="empresa_demo@test.com",
            password_hash="fake_hash_123",
            rol_id=1,
            estado="activo",
            foto_url="/uploads/avatars/avatar_demo.png"
        )
        db_session.add(sus)
        db_session.flush()

    # 2. Operador de la empresa
    op_id = uuid.UUID("00000000-0000-0000-0000-000000000020")
    op = db_session.query(CuentaUsuario).filter_by(id=op_id).first()
    if not op:
        op = CuentaUsuario(
            id=op_id,
            suscriptor_id=empresa_id,
            email="operador1@test.com",
            password_hash="fake_hash_123",
            nombre_completo="Juan Operador",
            rol_id=2,
            activo=True,
            foto_url="/uploads/avatars/avatar_op.png"
        )
        db_session.add(op)
        db_session.flush()

    # 3. Plan y Suscripción activa
    plan = db_session.query(PlanSuscripcion).filter_by(nombre="Profesional").first()
    if not plan:
        plan = PlanSuscripcion(
            nombre="Profesional",
            precio_mensual=29.99,
            descripcion="Plan profesional",
            activo=True
        )
        db_session.add(plan)
        db_session.flush()

    sub_id = uuid.UUID("00000000-0000-0000-0000-000000000030")
    sub = db_session.query(SuscripcionSuscriptor).filter_by(id=sub_id).first()
    if not sub:
        sub = SuscripcionSuscriptor(
            id=sub_id,
            suscriptor_id=empresa_id,
            plan_id=plan.id,
            inicia_en=datetime.now(timezone.utc) - timedelta(days=15),
            expira_en=datetime.now(timezone.utc) + timedelta(days=15),
            estado="activo"
        )
        db_session.add(sub)
        db_session.flush()

    # 4. Pagos realizados
    pago1 = PagoSuscriptor(
        id=uuid.uuid4(),
        suscriptor_id=empresa_id,
        monto=29.99,
        moneda="usd",
        estado="completado",
        plan_nombre="Profesional",
        fecha=datetime.now(timezone.utc) - timedelta(days=15)
    )
    pago2 = PagoSuscriptor(
        id=uuid.uuid4(),
        suscriptor_id=empresa_id,
        monto=29.99,
        moneda="usd",
        estado="completado",
        plan_nombre="Profesional",
        fecha=datetime.now(timezone.utc) - timedelta(days=45)
    )
    db_session.add_all([pago1, pago2])

    # 5. Campaña y Audio de Encuesta
    plantilla = PlantillaEncuesta(
        id=uuid.uuid4(),
        suscriptor_id=empresa_id,
        nombre="Plantilla Demo",
        descripcion="Desc",
        activo=True
    )
    db_session.add(plantilla)
    db_session.flush()

    campana = CampanaEncuesta(
        id=uuid.uuid4(),
        suscriptor_id=empresa_id,
        plantilla_id=plantilla.id,
        nombre="Campaña Satisfacción Q3",
        canal_id=1,
        estado_id=2
    )
    db_session.add(campana)
    db_session.flush()

    entrega = EntregaEncuesta(
        id=uuid.uuid4(),
        campana_id=campana.id,
        canal_id=1,
        estado_id=3
    )
    db_session.add(entrega)
    db_session.flush()

    audio = AudioRespuesta(
        id=uuid.uuid4(),
        entrega_id=entrega.id,
        archivo_url="/uploads/audio/respuesta_audio_1.mp3",
        formato="mp3",
        duracion_segundos=12.5,
        estado_transcripcion="completado",
        transcripcion_texto="Todo excelente con el servicio",
        creado_en=datetime.now(timezone.utc) - timedelta(days=2)
    )
    db_session.add(audio)

    # 6. Archivo subido por la empresa
    archivo_doc = ArchivoEmpresa(
        id=uuid.uuid4(),
        suscriptor_id=empresa_id,
        nombre="manual_corporativo.pdf",
        nombre_guardado="manual_corp_001.pdf",
        ruta="/uploads/archivos/manual_corp_001.pdf",
        extension=".pdf",
        peso_bytes=2048576,  # ~1.95 MB
        mime_type="application/pdf",
        categoria="documento",
        contexto="Políticas y Manuales",
        creado_por="empresa_demo@test.com",
        creado_en=datetime.now(timezone.utc) - timedelta(days=5)
    )
    db_session.add(archivo_doc)

    # 7. Registros de bitácora (AuditLog)
    ahora = datetime.now(timezone.utc)
    logs = [
        AuditLog(
            suscriptor_id=empresa_id,
            usuario_id=empresa_id,
            usuario_email="empresa_demo@test.com",
            rol="empresa",
            accion="LOGIN",
            modulo="AUTH",
            creado_en=ahora - timedelta(hours=2)
        ),
        AuditLog(
            suscriptor_id=empresa_id,
            usuario_id=empresa_id,
            usuario_email="empresa_demo@test.com",
            rol="empresa",
            accion="CREAR",
            modulo="CAMPANAS",
            creado_en=ahora - timedelta(days=1)
        ),
        AuditLog(
            suscriptor_id=empresa_id,
            usuario_id=op_id,
            usuario_email="operador1@test.com",
            rol="operator",
            accion="MODIFICAR",
            modulo="PLANTILLAS",
            creado_en=ahora - timedelta(days=1)
        ),
        AuditLog(
            suscriptor_id=empresa_id,
            usuario_id=op_id,
            usuario_email="operador1@test.com",
            rol="operator",
            accion="ELIMINAR",
            modulo="DESTINATARIOS",
            creado_en=ahora - timedelta(days=2)
        ),
        AuditLog(
            suscriptor_id=empresa_id,
            usuario_id=empresa_id,
            usuario_email="empresa_demo@test.com",
            rol="empresa",
            accion="CREAR",
            modulo="ARCHIVOS",
            creado_en=ahora - timedelta(days=2)
        ),
    ]
    db_session.add_all(logs)
    db_session.commit()

    return empresa_id

def test_consultar_archivos_empresa_listado(client, db_session, empresa_headers):
    empresa_id = setup_test_empresa_data(db_session)

    response = client.get("/archivos", headers=empresa_headers)
    assert response.status_code == 200
    data = response.json()

    assert "total" in data
    assert "limit" in data
    assert "offset" in data
    assert "espacio_total_usado_mb" in data
    assert "archivos" in data
    assert data["total"] >= 3  # Documento + Audio + Avatares

    # Validar que cada archivo contenga TODOS los campos mínimos y requeridos
    primer_archivo = data["archivos"][0]
    assert "archivo" in primer_archivo
    assert "extension" in primer_archivo
    assert "peso" in primer_archivo
    assert "unidad" in primer_archivo
    assert "peso_bytes" in primer_archivo
    assert "url_descarga" in primer_archivo
    assert "opcion_ver_descargar" in primer_archivo
    assert "mime_type" in primer_archivo
    assert "categoria" in primer_archivo
    assert "contexto" in primer_archivo
    assert "fecha_subida" in primer_archivo

    # Validar que la opción ver/descargar esté bien tipada
    opciones = primer_archivo["opcion_ver_descargar"]
    assert "ver" in opciones
    assert "descargar" in opciones
    assert "url" in opciones

def test_consultar_archivos_empresa_filtro_y_alias(client, db_session, empresa_headers):
    setup_test_empresa_data(db_session)

    # Alias /empresa/archivos
    res_alias = client.get("/empresa/archivos?categoria=audio_respuesta", headers=empresa_headers)
    assert res_alias.status_code == 200
    data_audio = res_alias.json()
    assert all(a["categoria"] == "audio_respuesta" for a in data_audio["archivos"])
    assert any(a["extension"] == ".mp3" for a in data_audio["archivos"])

    # Filtro por documento
    res_doc = client.get("/archivos?categoria=documento", headers=empresa_headers)
    assert res_doc.status_code == 200
    data_doc = res_doc.json()
    assert all(a["categoria"] == "documento" for a in data_doc["archivos"])
    assert any(a["archivo"] == "manual_corporativo.pdf" for a in data_doc["archivos"])

def test_subir_y_eliminar_archivo_empresa(client, db_session, empresa_headers):
    setup_test_empresa_data(db_session)

    file_content = b"Contenido de prueba para archivo subido de la empresa"
    files = {
        "file": ("prueba_subida.txt", BytesIO(file_content), "text/plain")
    }
    data = {
        "categoria": "documento",
        "contexto": "Test Automatizado"
    }

    upload_res = client.post("/archivos/upload", headers=empresa_headers, files=files, data=data)
    assert upload_res.status_code == 201
    created = upload_res.json()

    assert created["archivo"] == "prueba_subida.txt"
    assert created["extension"] == ".txt"
    assert created["peso_bytes"] == len(file_content)
    assert created["unidad"] in ["Bytes", "KB", "MB"]
    assert created["url_descarga"].startswith("/uploads/archivos/")

    # Eliminar el archivo
    archivo_id = created["id"]
    del_res = client.delete(f"/archivos/{archivo_id}", headers=empresa_headers)
    assert del_res.status_code == 200

def test_consultar_uso_sistema_metricas_completas(client, db_session, empresa_headers):
    setup_test_empresa_data(db_session)

    # Probar endpoint principal /analytics/uso-sistema
    response = client.get("/analytics/uso-sistema?dias=30", headers=empresa_headers)
    assert response.status_code == 200
    data = response.json()

    # 1. Última sesión
    assert data["ultima_sesion"] is not None
    assert "T" in data["ultima_sesion"]

    # 2. Espacio usado
    espacio = data["espacio_usado"]
    assert "bytes" in espacio
    assert "mb" in espacio
    assert "limite_mb" in espacio
    assert "porcentaje_usado" in espacio
    assert "unidad" in espacio
    assert "formateado" in espacio
    assert espacio["limite_mb"] == 1000.0  # Plan Profesional
    assert espacio["porcentaje_usado"] >= 0.0

    # 3. Pago total que ha realizado hasta la fecha
    assert "pago_total_acumulado" in data
    assert data["pago_total_acumulado"] == 59.98  # 29.99 * 2
    assert data["moneda"] == "usd"

    # 4. Frecuencia de pago
    assert data["frecuencia_pago"] == "Mensual"
    assert data["plan_nombre"] == "Profesional"
    assert data["estado_suscripcion"] == "activo"

    # 5. Gráfica con días de mayor uso
    grafica = data["grafica_dias_mayor_uso"]
    assert isinstance(grafica, list)
    assert len(grafica) > 0
    assert "fecha" in grafica[0]
    assert "cantidad" in grafica[0]
    assert data["dia_pico"] is not None

    # 6. Los 5 usuarios con más actividad en el sistema
    top_users = data["top_5_usuarios"]
    assert isinstance(top_users, list)
    assert len(top_users) <= 5
    assert len(top_users) > 0
    user_emails = [u["email"] for u in top_users]
    assert "empresa_demo@test.com" in user_emails

    # 7. Tipos de operaciones realizadas, gráfico torta (CUD)
    cud = data["tipos_operaciones_cud"]
    assert "crear" in cud
    assert "modificar" in cud
    assert "eliminar" in cud
    assert "otros" in cud
    assert "total" in cud
    assert "porcentajes" in cud
    assert cud["crear"] >= 2  # CREAR CAMPANAS, CREAR ARCHIVOS
    assert cud["modificar"] >= 1  # MODIFICAR PLANTILLAS
    assert cud["eliminar"] >= 1  # ELIMINAR DESTINATARIOS
    assert cud["total"] == cud["crear"] + cud["modificar"] + cud["eliminar"] + cud["otros"]
    assert "crear" in cud["porcentajes"]

def test_consultar_uso_sistema_endpoint_alias_empresa(client, db_session, empresa_headers):
    setup_test_empresa_data(db_session)

    # Probar endpoint alias /empresa/uso-sistema
    res_alias = client.get("/empresa/uso-sistema", headers=empresa_headers)
    assert res_alias.status_code == 200
    data = res_alias.json()
    assert data["frecuencia_pago"] == "Mensual"
    assert data["pago_total_acumulado"] == 59.98
