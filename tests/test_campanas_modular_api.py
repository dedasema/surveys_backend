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
    response = client.patch(f"/campanas/{campana_id}", json=invalid_transition_payload, headers=empresa_headers)
    assert response.status_code == 400
    assert "Transición no permitida" in response.json()["detail"]

    # 7. Delete Campaña via DELETE /campanas/{id}
    response = client.delete(f"/campanas/{campana_id}", headers=empresa_headers)
    assert response.status_code == 204

    # Verify not found after delete
    response = client.get(f"/campanas/{campana_id}", headers=empresa_headers)
    assert response.status_code == 404
