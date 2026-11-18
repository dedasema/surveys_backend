# tests/test_subscription_lifecycle.py
import uuid
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, AsyncMock

from app.models.suscriptor import Suscriptor
from app.models.subscription import PlanSuscripcion, SuscripcionSuscriptor
from app.models.survey import PlantillaEncuesta
from app.services.pagofacil_service import activar_suscripcion_por_pago
from app.models.pagofacil import PagoFacilTransaccion

def setup_lifecycle_data(db_session):
    empresa_id = uuid.UUID("00000000-0000-0000-0000-000000000002")
    sus = db_session.query(Suscriptor).filter_by(id=empresa_id).first()
    if not sus:
        sus = Suscriptor(
            id=empresa_id,
            nombre="Empresa Lifecycle SRL",
            email="lifecycle@empresa.com",
            telefono="77123456",
            password_hash="fake_hash_123",
            rol_id=1,
            estado="activo"
        )
        db_session.add(sus)

    # Planes
    plan_gratis = db_session.query(PlanSuscripcion).filter_by(nombre="Gratuito Lifecycle").first()
    if not plan_gratis:
        plan_gratis = PlanSuscripcion(
            nombre="Gratuito Lifecycle",
            precio_mensual=0.0,
            max_plantillas=3,
            max_campanas=2,
            max_operadores=1,
            activo=True
        )
        db_session.add(plan_gratis)

    plan_pro = db_session.query(PlanSuscripcion).filter_by(nombre="Profesional Lifecycle").first()
    if not plan_pro:
        plan_pro = PlanSuscripcion(
            nombre="Profesional Lifecycle",
            precio_mensual=30.0,
            max_plantillas=10,
            max_campanas=10,
            max_operadores=5,
            activo=True
        )
        db_session.add(plan_pro)

    plan_ent = db_session.query(PlanSuscripcion).filter_by(nombre="Enterprise Lifecycle").first()
    if not plan_ent:
        plan_ent = PlanSuscripcion(
            nombre="Enterprise Lifecycle",
            precio_mensual=90.0,
            max_plantillas=50,
            max_campanas=50,
            max_operadores=20,
            activo=True
        )
        db_session.add(plan_ent)

    db_session.commit()
    return empresa_id, plan_gratis, plan_pro, plan_ent

def test_upgrade_con_credito_prorrateo(client, db_session, empresa_headers):
    """
    Verifica que al hacer Upgrade de Pro ($30) a Enterprise ($90) a mitad de mes,
    se aplique el crédito por días no consumidos y el monto sea menor a $90 * TC.
    """
    empresa_id, plan_gratis, plan_pro, plan_ent = setup_lifecycle_data(db_session)

    # Suscripción Pro activa con 20 días restantes de 30
    ahora = datetime.now(timezone.utc)
    sub_pro = SuscripcionSuscriptor(
        suscriptor_id=empresa_id,
        plan_id=plan_pro.id,
        inicia_en=ahora - timedelta(days=10),
        expira_en=ahora + timedelta(days=20),
        estado="activo"
    )
    db_session.add(sub_pro)
    db_session.commit()

    with patch("app.services.pagofacil_service.obtener_tipo_cambio_oficial", new_callable=AsyncMock) as mock_tc:
        mock_tc.return_value = (10.0, False, {})  # 1 USD = 10 BOB

        res = client.post("/pagofacil/generar-qr", json={"plan_id": plan_ent.id}, headers=empresa_headers)
        assert res.status_code == 201
        data = res.json()

        # Si el plan Enterprise vale $90 * 10 = 900 BOB precio completo
        # Con 20 días restantes de Pro ($30 * 20/30 = $20 de crédito)
        # El precio a cobrar es $90 - $20 = $70 USD -> 700 BOB
        assert data["monto_real_bob"] < 900.0
        assert data["monto_real_bob"] == 700.0

def test_downgrade_bloqueado_por_exceso_de_plantillas(client, db_session, empresa_headers):
    """
    Verifica que si la empresa tiene 5 plantillas creadas y quiere bajarse al Gratuito (máx 3),
    el sistema rechace la solicitud con error explicativo 400.
    """
    empresa_id, plan_gratis, plan_pro, plan_ent = setup_lifecycle_data(db_session)

    # Suscripción Pro activa
    sub_pro = db_session.query(SuscripcionSuscriptor).filter_by(suscriptor_id=empresa_id, estado="activo").first()
    if not sub_pro:
        sub_pro = SuscripcionSuscriptor(
            suscriptor_id=empresa_id,
            plan_id=plan_pro.id,
            inicia_en=datetime.now(timezone.utc),
            expira_en=datetime.now(timezone.utc) + timedelta(days=20),
            estado="activo"
        )
        db_session.add(sub_pro)
        db_session.commit()

    # Crear 5 plantillas para la empresa
    for i in range(5):
        p = PlantillaEncuesta(
            id=uuid.uuid4(),
            suscriptor_id=empresa_id,
            nombre=f"Plantilla Test {i+1}",
            descripcion="Test"
        )
        db_session.add(p)
    db_session.commit()

    res = client.post("/pagofacil/generar-qr", json={"plan_id": plan_gratis.id}, headers=empresa_headers)
    assert res.status_code == 400
    assert "plantillas creadas" in res.json()["detail"]

def test_downgrade_programado_al_fin_de_ciclo(client, db_session, empresa_headers):
    """
    Verifica que si la empresa tiene recursos compatibles pero su plan sigue vigente,
    el cambio a plan menor se programe para el fin del período sin cobro hoy.
    """
    empresa_id, plan_gratis, plan_pro, plan_ent = setup_lifecycle_data(db_session)

    # Limpiar plantillas anteriores para que tenga solo 1
    db_session.query(PlantillaEncuesta).filter_by(suscriptor_id=empresa_id).delete()
    p1 = PlantillaEncuesta(
        id=uuid.uuid4(),
        suscriptor_id=empresa_id,
        nombre="Plantilla Única",
        descripcion="Test"
    )
    db_session.add(p1)
    db_session.commit()

    # Plan Pro vigente por 15 días más
    sub_pro = db_session.query(SuscripcionSuscriptor).filter_by(suscriptor_id=empresa_id, estado="activo").first()
    if not sub_pro:
        sub_pro = SuscripcionSuscriptor(
            suscriptor_id=empresa_id,
            plan_id=plan_pro.id,
            inicia_en=datetime.now(timezone.utc) - timedelta(days=15),
            expira_en=datetime.now(timezone.utc) + timedelta(days=15),
            estado="activo"
        )
        db_session.add(sub_pro)
    else:
        sub_pro.plan_id = plan_pro.id
        sub_pro.expira_en = datetime.now(timezone.utc) + timedelta(days=15)
    db_session.commit()

    res = client.post("/pagofacil/generar-qr", json={"plan_id": plan_gratis.id}, headers=empresa_headers)
    assert res.status_code == 201
    data = res.json()
    assert data["status"] == "programado"
    assert data["monto_real_bob"] == 0.0
    assert "se mantendrá activo" in data["mensaje"]

def test_renovacion_misma_suscripcion_extiende_fecha(db_session):
    """
    Verifica que al pagar la renovación del mismo plan vigente,
    la fecha de expiración se extienda sumando 30 días a la fecha que ya tenía.
    """
    empresa_id, plan_gratis, plan_pro, plan_ent = setup_lifecycle_data(db_session)

    # Suscripción Pro activa con 10 días restantes
    ahora = datetime.now(timezone.utc)
    expira_original = ahora + timedelta(days=10)
    sub = SuscripcionSuscriptor(
        suscriptor_id=empresa_id,
        plan_id=plan_pro.id,
        inicia_en=ahora - timedelta(days=20),
        expira_en=expira_original,
        estado="activo"
    )
    db_session.add(sub)
    db_session.commit()

    tx = PagoFacilTransaccion(
        payment_number=f"PF-RENOV-{uuid.uuid4().hex[:6]}",
        suscriptor_id=empresa_id,
        plan_id=plan_pro.id,
        monto=300.0,
        monto_qr=0.3,
        moneda="BOB",
        tipo_cambio=10.0,
        estado="pendiente"
    )
    db_session.add(tx)
    db_session.commit()

    # Ejecutar activación por pago
    activar_suscripcion_por_pago(db_session, tx)

    # Verificar nueva suscripción
    nueva_sub = (
        db_session.query(SuscripcionSuscriptor)
        .filter_by(suscriptor_id=empresa_id, estado="activo")
        .order_by(SuscripcionSuscriptor.inicia_en.desc())
        .first()
    )
    assert nueva_sub is not None
    # La nueva fecha debe ser aproximadamente expira_original + 30 días (40 días desde ahora)
    exp_dt = nueva_sub.expira_en.replace(tzinfo=None) if nueva_sub.expira_en else None
    ahora_dt = ahora.replace(tzinfo=None)
    delta_dias = (exp_dt - ahora_dt).days
    assert delta_dias >= 39
