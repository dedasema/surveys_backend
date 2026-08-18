# app/services/excel_export_service.py
import io
from uuid import UUID
from datetime import datetime
from sqlalchemy.orm import Session
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from app.models.survey import CampanaEncuesta, EntregaEncuesta, RespuestaEncuesta, RespuestaPregunta, PreguntaEncuesta, OpcionEncuesta, Destinatario
from app.models.catalogos import Canal, EstadoCampana

def generar_excel_respuestas_campana(db: Session, campana_id: UUID) -> io.BytesIO:
    """
    Genera un archivo Excel (.xlsx) estructurado y profesional con dos hojas:
    1. Resumen y KPIs de la Campaña.
    2. Matriz detallada de Respuestas por Pregunta.
    """
    campana = db.query(CampanaEncuesta).filter(CampanaEncuesta.id == campana_id).first()
    if not campana:
        raise ValueError("Campaña no encontrada")

    # 1. Obtener preguntas de la plantilla asociadas en orden
    preguntas = []
    if campana.plantilla:
        preguntas = (
            db.query(PreguntaEncuesta)
            .filter(PreguntaEncuesta.plantilla_id == campana.plantilla.id)
            .order_by(PreguntaEncuesta.orden)
            .all()
        )

    # 2. Obtener entregas y respuestas
    entregas = (
        db.query(EntregaEncuesta)
        .filter(EntregaEncuesta.campana_id == campana_id)
        .order_by(EntregaEncuesta.enviado_en.desc())
        .all()
    )

    total_entregas = len(entregas)
    entregas_respondidas = [e for e in entregas if e.respondido_en is not None or len(e.respuestas) > 0]
    total_respuestas = len(entregas_respondidas)
    tasa_respuesta = (total_respuestas / total_entregas * 100) if total_entregas > 0 else 0.0

    canal_nombre = "Desconocido"
    if campana.canal_id:
        canal_obj = db.query(Canal).filter(Canal.id == campana.canal_id).first()
        if canal_obj:
            canal_nombre = canal_obj.nombre.capitalize()

    estado_nombre = "Activa"
    if campana.estado_id:
        estado_obj = db.query(EstadoCampana).filter(EstadoCampana.id == campana.estado_id).first()
        if estado_obj:
            estado_nombre = estado_obj.nombre.capitalize()

    # Iniciar libro OpenPyXL
    wb = openpyxl.Workbook()
    
    # ─────────────────────────────────────────────────────────────
    # HOJA 1: RESUMEN Y KPIS
    # ─────────────────────────────────────────────────────────────
    ws_resumen = wb.active
    ws_resumen.title = "Resumen de Campana"
    ws_resumen.views.sheetView[0].showGridLines = True

    # Estilos
    font_titulo = Font(name="Calibri", size=16, bold=True, color="1E293B")
    font_subtitulo = Font(name="Calibri", size=11, color="64748B")
    font_header = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    font_bold = Font(name="Calibri", size=11, bold=True, color="0F172A")
    font_data = Font(name="Calibri", size=11, color="334155")
    
    fill_header = PatternFill(start_color="1E3A8A", end_color="1E3A8A", fill_type="solid") # Navy Blue
    fill_alt = PatternFill(start_color="F1F5F9", end_color="F1F5F9", fill_type="solid")
    fill_kpi = PatternFill(start_color="EFF6FF", end_color="EFF6FF", fill_type="solid")

    border_thin = Border(
        left=Side(style='thin', color='CBD5E1'),
        right=Side(style='thin', color='CBD5E1'),
        top=Side(style='thin', color='CBD5E1'),
        bottom=Side(style='thin', color='CBD5E1')
    )

    # Título
    ws_resumen["B2"] = f"REPORTE EJECUTIVO DE CAMPAÑA: {campana.nombre.upper()}"
    ws_resumen["B2"].font = font_titulo
    ws_resumen["B3"] = f"Generado el: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | Sistema SurveySaaS"
    ws_resumen["B3"].font = font_subtitulo

    # Tabla de Metadatos
    metadata_rows = [
        ("Campaña ID", str(campana.id)),
        ("Nombre de Campaña", campana.nombre),
        ("Plantilla Asociada", campana.plantilla.nombre if campana.plantilla else "Sin plantilla"),
        ("Canal Principal", canal_nombre),
        ("Estado de Campaña", estado_nombre),
        ("Fecha de Creación", campana.creado_en.strftime("%Y-%m-%d %H:%M") if campana.creado_en else "N/A"),
        ("Fecha Programada", campana.programada_en.strftime("%Y-%m-%d %H:%M") if campana.programada_en else "Inmediata"),
    ]

    ws_resumen["B5"] = "Información General"
    ws_resumen["B5"].font = font_bold
    ws_resumen.merge_cells("B5:C5")

    for i, (k, v) in enumerate(metadata_rows, start=6):
        ws_resumen[f"B{i}"] = k
        ws_resumen[f"B{i}"].font = font_bold
        ws_resumen[f"B{i}"].fill = fill_alt
        ws_resumen[f"B{i}"].border = border_thin

        ws_resumen[f"C{i}"] = v
        ws_resumen[f"C{i}"].font = font_data
        ws_resumen[f"C{i}"].border = border_thin

    # Tarjetas KPIs
    kpis = [
        ("Total Destinatarios", total_entregas),
        ("Respuestas Recibidas", total_respuestas),
        ("Tasa de Respuesta", f"{tasa_respuesta:.1f}%"),
        ("Total Preguntas", len(preguntas)),
    ]

    ws_resumen["E5"] = "Métricas Clave"
    ws_resumen["E5"].font = font_bold
    ws_resumen.merge_cells("E5:F5")

    for i, (k, v) in enumerate(kpis, start=6):
        ws_resumen[f"E{i}"] = k
        ws_resumen[f"E{i}"].font = font_bold
        ws_resumen[f"E{i}"].fill = fill_kpi
        ws_resumen[f"E{i}"].border = border_thin

        ws_resumen[f"F{i}"] = v
        ws_resumen[f"F{i}"].font = font_bold
        ws_resumen[f"F{i}"].alignment = Alignment(horizontal="center")
        ws_resumen[f"F{i}"].border = border_thin

    # Ajuste de anchos Hoja Resumen
    ws_resumen.column_dimensions["A"].width = 4
    ws_resumen.column_dimensions["B"].width = 24
    ws_resumen.column_dimensions["C"].width = 45
    ws_resumen.column_dimensions["D"].width = 4
    ws_resumen.column_dimensions["E"].width = 24
    ws_resumen.column_dimensions["F"].width = 18

    # ─────────────────────────────────────────────────────────────
    # HOJA 2: MATRIZ DETALLADA DE RESPUESTAS
    # ─────────────────────────────────────────────────────────────
    ws_respuestas = wb.create_sheet(title="Matriz de Respuestas")
    ws_respuestas.views.sheetView[0].showGridLines = True

    # Encabezados base
    headers = [
        "#",
        "ID Entrega",
        "Destinatario",
        "Email / Teléfono",
        "Canal",
        "Fecha de Envío",
        "Fecha de Respuesta",
        "Puntuación",
    ]

    # Agregar encabezados por cada pregunta
    for p in preguntas:
        headers.append(f"P{p.orden}: {p.texto}")
    
    headers.append("Sentimiento / NLP")

    # Escribir encabezados
    ws_respuestas.row_dimensions[1].height = 28
    for col_num, header_text in enumerate(headers, start=1):
        cell = ws_respuestas.cell(row=1, column=col_num, value=header_text)
        cell.font = font_header
        cell.fill = fill_header
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = border_thin

    # Construir mapa de opciones por id para resolución rápida de texto
    opciones_map = {}
    for p in preguntas:
        for op in p.opciones:
            opciones_map[op.id] = op.texto

    # Llenar datos de entregas
    row_idx = 2
    for idx, entrega in enumerate(entregas, start=1):
        resp_obj = entrega.respuestas[0] if entrega.respuestas else None
        
        # Mapear respuestas a cada pregunta
        resp_preguntas_dict = {}
        sentimiento_texto = "N/A"
        
        if resp_obj:
            for rp in resp_obj.respuestas_preguntas:
                valor = ""
                if rp.opcion_id and rp.opcion_id in opciones_map:
                    valor = opciones_map[rp.opcion_id]
                elif rp.texto:
                    valor = rp.texto
                elif rp.numero is not None:
                    valor = str(rp.numero)
                
                resp_preguntas_dict[rp.pregunta_id] = valor

                if rp.metadatos and isinstance(rp.metadatos, dict):
                    if "sentimiento" in rp.metadatos:
                        sentimiento_texto = str(rp.metadatos["sentimiento"]).capitalize()

        dest_nombre = entrega.destinatario.nombre if entrega.destinatario else "Anónimo"
        dest_contacto = (
            entrega.destinatario.email or entrega.destinatario.telefono
            if entrega.destinatario else "Enlace público"
        )

        row_data = [
            idx,
            str(entrega.id),
            dest_nombre,
            dest_contacto,
            canal_nombre,
            entrega.enviado_en.strftime("%Y-%m-%d %H:%M") if entrega.enviado_en else "N/A",
            entrega.respondido_en.strftime("%Y-%m-%d %H:%M") if entrega.respondido_en else "No respondida",
            float(resp_obj.puntuacion) if resp_obj and resp_obj.puntuacion is not None else "N/A",
        ]

        # Agregar columnas de cada pregunta
        for p in preguntas:
            row_data.append(resp_preguntas_dict.get(p.id, "-"))

        row_data.append(sentimiento_texto)

        # Escribir fila
        ws_respuestas.row_dimensions[row_idx].height = 20
        fill_row = fill_alt if row_idx % 2 == 0 else None

        for col_num, val in enumerate(row_data, start=1):
            cell = ws_respuestas.cell(row=row_idx, column=col_num, value=val)
            cell.font = font_data
            cell.border = border_thin
            if fill_row:
                cell.fill = fill_row
            if col_num in [1, 5, 6, 7, 8]:
                cell.alignment = Alignment(horizontal="center", vertical="center")
            else:
                cell.alignment = Alignment(vertical="center")

        row_idx += 1

    # Autoajustar ancho de columnas en Matriz de Respuestas
    for col in ws_respuestas.columns:
        max_len = 0
        col_letter = get_column_letter(col[0].column)
        for cell in col:
            val_str = str(cell.value or "")
            if len(val_str) > max_len:
                max_len = len(val_str)
        adjusted_width = min(max(max_len + 3, 10), 45)
        ws_respuestas.column_dimensions[col_letter].width = adjusted_width

    # Guardar en memoria
    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return output
