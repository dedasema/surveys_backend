# tests/test_excel_export.py
import openpyxl
from app.services.excel_export_service import generar_excel_respuestas_campana
from app.models.survey import CampanaEncuesta, PlantillaEncuesta, PreguntaEncuesta, EntregaEncuesta, Destinatario
from app.models.catalogos import Canal, EstadoCampana
import uuid

def test_generar_excel_respuestas_campana(db_session):
    # Crear datos de prueba
    sus_id = uuid.uuid4()
    canal = Canal(id=1, nombre="Web")
    estado = EstadoCampana(id=1, nombre="Activa")
    plantilla = PlantillaEncuesta(id=uuid.uuid4(), suscriptor_id=sus_id, nombre="Encuesta NPS Test", activo=True)
    db_session.add_all([canal, estado, plantilla])
    db_session.commit()

    p1 = PreguntaEncuesta(id=uuid.uuid4(), plantilla_id=plantilla.id, orden=1, texto="Calificación 1-10", tipo_pregunta_id=2, obligatorio=True)
    db_session.add(p1)
    db_session.commit()

    campana = CampanaEncuesta(
        id=uuid.uuid4(),
        suscriptor_id=sus_id,
        plantilla_id=plantilla.id,
        nombre="Campaña Test Excel",
        canal_id=1,
        estado_id=1
    )
    dest = Destinatario(id=uuid.uuid4(), suscriptor_id=sus_id, nombre="Juan Perez", email="juan@test.com")
    db_session.add_all([campana, dest])
    db_session.commit()

    entrega = EntregaEncuesta(id=uuid.uuid4(), campana_id=campana.id, destinatario_id=dest.id, canal_id=1)
    db_session.add(entrega)
    db_session.commit()

    # Generar Excel
    stream = generar_excel_respuestas_campana(db_session, campana.id)
    assert stream is not None
    
    # Validar libro con openpyxl
    wb = openpyxl.load_workbook(stream)
    sheet_names = wb.sheetnames
    assert "Resumen de Campana" in sheet_names
    assert "Matriz de Respuestas" in sheet_names

    ws_resumen = wb["Resumen de Campana"]
    assert "REPORTE EJECUTIVO DE CAMPAÑA: CAMPAÑA TEST EXCEL" in str(ws_resumen["B2"].value)

    ws_respuestas = wb["Matriz de Respuestas"]
    assert ws_respuestas.cell(row=1, column=1).value == "#"
    assert ws_respuestas.cell(row=1, column=3).value == "Destinatario"
