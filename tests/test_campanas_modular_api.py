"""
Integration tests for the Modular Campanas Router and Use Cases.
"""

from uuid import UUID
from datetime import datetime, timezone, timedelta

from app.models.suscriptor import Suscriptor
from app.models.survey import PlantillaEncuesta


def test_crud_campanas_modular_flow(client, db_session, empresa_headers):
    # 1. Setup Suscriptor activo
    empresa_id = UUID("00000000-0000-0000-0000-000000000002")
    suscriptor = db_session.get(Suscriptor, empresa_id)
    if not suscriptor:
        suscriptor = Suscriptor(
            id=empresa_id,
            nombre="Empresa Test",
            email="empresa@test.com",
            password_hash="dummy_hash",
            estado="activo",
        )
        db_session.add(suscriptor)
        db_session.commit()
    else:
        suscriptor.estado = "activo"
        db_session.commit()

    # 2. Setup Plantilla
    plantilla = PlantillaEncuesta(
        nombre="Plantilla Base",
        suscriptor_id=empresa_id,
    )
    db_session.add(plantilla)
    db_session.commit()
    db_session.refresh(plantilla)

    # 3. Create Campaña via POST /campanas
    create_payload = {
        "nombre": "Campaña Modular V1",
        "canal_id": 1,
        "plantilla_id": str(plantilla.id),
    }
    response = client.post("/campanas", json=create_payload, headers=empresa_headers)
    assert response.status_code == 201
    created_data = response.json()
    assert created_data["nombre"] == "Campaña Modular V1"
    assert created_data["estado_id"] == 1  # BORRADOR
    campana_id = created_data["id"]

    # 4. List Campañas via GET /campanas
    response = client.get("/campanas", headers=empresa_headers)
    assert response.status_code == 200
    campanas_list = response.json()
    assert any(c["id"] == campana_id for c in campanas_list)

    # 5. Programar Campaña via PATCH /campanas/{id}
    fecha_futura = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
    update_payload = {
        "estado_id": 2,  # PROGRAMADA
        "programada_en": fecha_futura,
    }
    response = client.patch(f"/campanas/{campana_id}", json=update_payload, headers=empresa_headers)
    assert response.status_code == 200
    assert response.json()["estado_id"] == 2

    # 6. Intentar transición inválida via PATCH (de PROGRAMADA directamente a CERRADA no permitido)
    invalid_transition_payload = {
        "estado_id": 4,  # CERRADA
    }
    response = client.patch(
        f"/campanas/{campana_id}",
        json=invalid_transition_payload,
        headers=empresa_headers,
    )
    assert response.status_code == 400
    assert "Transición no permitida" in response.json()["detail"]

    # 7. Delete Campaña via DELETE /campanas/{id}
    response = client.delete(f"/campanas/{campana_id}", headers=empresa_headers)
    assert response.status_code == 204

    # Verify not found after delete
    response = client.get(f"/campanas/{campana_id}", headers=empresa_headers)
    assert response.status_code == 404


def test_list_respuestas_endpoint_and_campaign_filter(client, db_session, empresa_headers):
    empresa_id = UUID("00000000-0000-0000-0000-000000000002")
    suscriptor = db_session.get(Suscriptor, empresa_id)
    if not suscriptor:
        suscriptor = Suscriptor(
            id=empresa_id,
            nombre="Empresa Test",
            email="empresa@test.com",
            password_hash="dummy_hash",
            estado="activo",
        )
        db_session.add(suscriptor)
        db_session.commit()

    plantilla = PlantillaEncuesta(
        nombre="Plantilla Respuestas",
        suscriptor_id=empresa_id,
    )
    db_session.add(plantilla)
    db_session.commit()
    db_session.refresh(plantilla)

    from app.models.survey import (
        CampanaEncuesta,
        EntregaEncuesta,
        RespuestaEncuesta,
        PreguntaEncuesta,
        RespuestaPregunta,
        Destinatario,
    )

    pregunta = PreguntaEncuesta(
        plantilla_id=plantilla.id,
        orden=1,
        texto="¿Cómo califica el servicio?",
        tipo_pregunta_id=1,
        obligatorio=True,
    )
    db_session.add(pregunta)
    db_session.commit()
    db_session.refresh(pregunta)

    campana = CampanaEncuesta(
        suscriptor_id=empresa_id,
        plantilla_id=plantilla.id,
        nombre="Campaña Test Respuestas",
        canal_id=1,
    )
    db_session.add(campana)
    db_session.commit()
    db_session.refresh(campana)

    dest = Destinatario(
        suscriptor_id=empresa_id,
        nombre="Cliente VIP",
        email="vip@cliente.com",
    )
    db_session.add(dest)
    db_session.commit()
    db_session.refresh(dest)

    entrega = EntregaEncuesta(
        campana_id=campana.id,
        destinatario_id=dest.id,
        canal_id=1,
        estado_id=3,
        respondido_en=datetime.now(timezone.utc),
    )
    db_session.add(entrega)
    db_session.commit()
    db_session.refresh(entrega)

    resp = RespuestaEncuesta(
        entrega_id=entrega.id,
        puntuacion=5.0,
    )
    db_session.add(resp)
    db_session.commit()
    db_session.refresh(resp)

    rp = RespuestaPregunta(
        respuesta_id=resp.id,
        pregunta_id=pregunta.id,
        texto="Excelente servicio",
        numero=5.0,
    )
    db_session.add(rp)
    db_session.commit()

    # 1. Test GET /respuestas?campana_id={campana.id}
    res = client.get(f"/respuestas?campana_id={campana.id}", headers=empresa_headers)
    assert res.status_code == 200
    data = res.json()
    assert len(data) >= 1
    item = next(d for d in data if d["id"] == str(resp.id))
    assert item["campana_id"] == str(campana.id)
    assert item["destinatario"]["nombre"] == "Cliente VIP"
    assert len(item["detalles"]) == 1
    assert item["detalles"][0]["pregunta"] == "¿Cómo califica el servicio?"
    assert item["detalles"][0]["valor"] == "Excelente servicio"

    # 2. Test GET /campanas/{campana.id}/respuestas
    res_camp = client.get(f"/campanas/{campana.id}/respuestas", headers=empresa_headers)
    assert res_camp.status_code == 200
    assert any(d["id"] == str(resp.id) for d in res_camp.json())

    # 3. Test GET /respuestas/{resp.id}
    res_single = client.get(f"/respuestas/{resp.id}", headers=empresa_headers)
    assert res_single.status_code == 200
    assert res_single.json()["id"] == str(resp.id)
