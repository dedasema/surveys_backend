# tests/test_audit_log.py
from app.services.audit_service import registrar_auditoria, listar_auditoria, contar_auditoria
from app.models.audit_log import AuditLog

def test_registrar_auditoria_service(db_session):
    log = registrar_auditoria(
        db=db_session,
        accion="CREAR",
        modulo="PLANTILLAS",
        usuario_email="test@empresa.com",
        rol="empresa",
        entidad_id="test-uuid-123",
        detalles={"nombre": "Plantilla de Prueba"}
    )
    assert log is not None
    assert log.accion == "CREAR"
    assert log.modulo == "PLANTILLAS"
    assert log.detalles["nombre"] == "Plantilla de Prueba"

def test_listar_y_contar_auditoria(db_session):
    registrar_auditoria(db=db_session, accion="LOGIN", modulo="AUTH", usuario_email="user1@test.com")
    registrar_auditoria(db=db_session, accion="ELIMINAR", modulo="ROLES", usuario_email="admin@test.com")

    total = contar_auditoria(db_session)
    assert total >= 2

    roles_logs = listar_auditoria(db_session, modulo="ROLES")
    assert len(roles_logs) >= 1
    assert roles_logs[0].modulo == "ROLES"

def test_auditoria_endpoints(client, admin_headers):
    res = client.get("/auditoria", headers=admin_headers)
    assert res.status_code == 200
    data = res.json()
    assert "total" in data
    assert "items" in data
    assert isinstance(data["items"], list)

    res_filtros = client.get("/auditoria/filtros", headers=admin_headers)
    assert res_filtros.status_code == 200
    filtros = res_filtros.json()
    assert "modulos" in filtros
    assert "acciones" in filtros
    assert "ROLES" in filtros["modulos"]
