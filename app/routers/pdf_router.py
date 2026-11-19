from uuid import UUID
from typing import List
import io, zipfile
try:
    import qrcode
except Exception:
    qrcode = None  # type: ignore

try:
    from reportlab.pdfgen.canvas import Canvas
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib.utils import ImageReader
except Exception:
    Canvas = None  # type: ignore
    A4 = None  # type: ignore
    mm = None  # type: ignore
    ImageReader = None  # type: ignore

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session, joinedload



from app.core.constants import ESTADO_RESPONDIDO
from app.core.database import get_db
from app.models.survey import EntregaEncuesta, PreguntaEncuesta

router = APIRouter(prefix="/entregas", tags=["PDF / Formularios"])

PAGE_W, PAGE_H = A4 if A4 else (595.27, 841.89)
mm_val          = mm if mm else 2.83465
TOP_MARGIN      = 20 * mm_val
BOTTOM_MARGIN   = 20 * mm_val
QR_SIZE         = 45 * mm_val
LINE_HEIGHT     = 5  * mm_val
BOX_SIZE        = 4  * mm_val

TEXT_SIZE       = 9
TITLE_SIZE      = 14


def _draw_checkbox(c: Canvas, x: float, baseline_y: float):
    c.rect(x, baseline_y - BOX_SIZE + 1, BOX_SIZE, BOX_SIZE, stroke=1, fill=0)


def _build_pdf(entrega: EntregaEncuesta, preguntas: List[PreguntaEncuesta]) -> io.BytesIO:
    buf = io.BytesIO()
    c = Canvas(buf, pagesize=A4)
    
    _render_survey_page(c, entrega, preguntas)
    
    c.save()
    buf.seek(0)
    return buf


@router.get("/{entrega_id}/formulario.pdf")
async def pdf_por_entrega(entrega_id: UUID, db: Session = Depends(get_db)):
    if Canvas is None or qrcode is None:
        raise HTTPException(500, "Módulos de generación PDF no disponibles. Contacte al administrador.")
    ent = (
        db.query(EntregaEncuesta)
        .options(joinedload(EntregaEncuesta.campana))
        .filter(EntregaEncuesta.id == entrega_id)
        .first()
    )
    if not ent:
        raise HTTPException(404, "Entrega no encontrada")

    preguntas = (
        db.query(PreguntaEncuesta)
        .options(joinedload(PreguntaEncuesta.opciones))
        .filter(PreguntaEncuesta.plantilla_id == ent.campana.plantilla_id)
        .order_by(PreguntaEncuesta.orden)
        .all()
    )

    pdf = _build_pdf(ent, preguntas)
    headers = {"Content-Disposition": f'attachment; filename="{ent.id}.pdf"'}
    return StreamingResponse(pdf, media_type="application/pdf", headers=headers)


@router.get("/campanas/{campana_id}/formularios.zip")
async def pdf_bulk(campana_id: UUID, db: Session = Depends(get_db)):
    entregas = (
        db.query(EntregaEncuesta)
        .options(joinedload(EntregaEncuesta.campana))
        .filter(EntregaEncuesta.campana_id == campana_id)
        .order_by(EntregaEncuesta.id)
        .all()
    )
    if not entregas:
        raise HTTPException(404, "Sin entregas para esta campaña")

    plantilla_id = entregas[0].campana.plantilla_id
    preguntas = (
        db.query(PreguntaEncuesta)
        .options(joinedload(PreguntaEncuesta.opciones))
        .filter(PreguntaEncuesta.plantilla_id == plantilla_id)
        .order_by(PreguntaEncuesta.orden)
        .all()
    )

    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w") as zf:
        for ent in entregas:
            pdf_bytes = _build_pdf(ent, preguntas).getvalue()
            zf.writestr(f"{ent.id}.pdf", pdf_bytes)
    zip_buf.seek(0)

    headers = {"Content-Disposition": f'attachment; filename="formularios_{campana_id}.zip"'}
    return StreamingResponse(zip_buf, media_type="application/zip", headers=headers)


@router.get("/campanas/{campana_id}/formularios.pdf")
async def pdf_combined(campana_id: UUID, db: Session = Depends(get_db)):
    if Canvas is None or qrcode is None:
        raise HTTPException(500, "Módulos de generación PDF no disponibles. Contacte al administrador.")
    entregas = (
        db.query(EntregaEncuesta)
        .options(joinedload(EntregaEncuesta.campana))
        .filter(
            EntregaEncuesta.campana_id == campana_id,
            EntregaEncuesta.estado_id != ESTADO_RESPONDIDO  # Solo entregas no respondidas
        )
        .order_by(EntregaEncuesta.id)
        .all()
    )
    if not entregas:
        # Si no hay entregas pendientes, buscar cualquier entrega previa de la campaña
        entregas = (
            db.query(EntregaEncuesta)
            .options(joinedload(EntregaEncuesta.campana))
            .filter(EntregaEncuesta.campana_id == campana_id)
            .order_by(EntregaEncuesta.id)
            .all()
        )
        if not entregas:
            # Si la campaña aún no tiene entregas, auto-crear 1 entrega por papel para generar el formulario PDF
            from app.services.entregas_service import create_bulk_entregas_papel
            from app.services.campanas_service import get_campana
            campana = get_campana(db, campana_id)
            if not campana:
                raise HTTPException(404, "Campaña no encontrada")
            entregas = create_bulk_entregas_papel(db, campana_id, 1)

    plantilla_id = entregas[0].campana.plantilla_id
    preguntas = (
        db.query(PreguntaEncuesta)
        .options(joinedload(PreguntaEncuesta.opciones))
        .filter(PreguntaEncuesta.plantilla_id == plantilla_id)
        .order_by(PreguntaEncuesta.orden)
        .all()
    )

    buf = io.BytesIO()
    c = Canvas(buf, pagesize=A4)
    
    for i, entrega in enumerate(entregas):
        if i > 0:
            c.showPage()
        
        _render_survey_page(c, entrega, preguntas)
    
    c.save()
    buf.seek(0)

    headers = {"Content-Disposition": f'attachment; filename="formularios_{campana_id}.pdf"'}
    return StreamingResponse(buf, media_type="application/pdf", headers=headers)


def _render_survey_page(c: Canvas, entrega: EntregaEncuesta, preguntas: List[PreguntaEncuesta]):
    y = PAGE_H - TOP_MARGIN  

    qr_img = qrcode.make(str(entrega.id))
    qr_buf = io.BytesIO()
    qr_img.save(qr_buf, format="PNG")
    qr_buf.seek(0)
    qr_reader = ImageReader(qr_buf)
    c.drawImage(qr_reader, (PAGE_W - QR_SIZE) / 2, y - QR_SIZE, QR_SIZE, QR_SIZE)
    y -= QR_SIZE + 8 * mm

    c.setFont("Helvetica-Bold", TITLE_SIZE)
    c.drawCentredString(PAGE_W / 2, y, entrega.campana.nombre)
    y -= TITLE_SIZE
    
    y -= LINE_HEIGHT * 3

    c.setFont("Helvetica", TEXT_SIZE)

    for p in preguntas:
        c.drawString(15 * mm, y, f"{p.orden}. {p.texto}")
        y -= LINE_HEIGHT

        if p.tipo_pregunta_id == 3:
            c.setFont("Helvetica", TEXT_SIZE - 1)
            c.drawString(17 * mm, y, "(una opción)")
            c.setFont("Helvetica", TEXT_SIZE)
            y -= LINE_HEIGHT
        elif p.tipo_pregunta_id == 4:
            c.setFont("Helvetica", TEXT_SIZE - 1)
            c.drawString(17 * mm, y, "(varias opciones)")
            c.setFont("Helvetica", TEXT_SIZE)
            y -= LINE_HEIGHT

        if p.tipo_pregunta_id in (3, 4):
            for opt in p.opciones:
                _draw_checkbox(c, 20 * mm, y + BOX_SIZE / 2)
                c.drawString(25 * mm, y, opt.texto)
                y -= LINE_HEIGHT

        elif p.tipo_pregunta_id == 1:
            y -= LINE_HEIGHT * 0.5
            
            for _ in range(2):
                c.line(20 * mm, y, PAGE_W - 20 * mm, y)
                y -= LINE_HEIGHT * 1.5

        elif p.tipo_pregunta_id == 2:
            y -= LINE_HEIGHT * 0.5
            
            c.line(20 * mm, y, 70 * mm, y)
            y -= LINE_HEIGHT * 1.5

        y -= LINE_HEIGHT * 0.5  

        if y < BOTTOM_MARGIN + 20 * mm:
            break

    # Pie de página de marca oficial (B4)
    c.setFont("Helvetica-Oblique", 8)
    c.setFillColorRGB(0.35, 0.35, 0.35)
    c.drawCentredString(PAGE_W / 2, 10 * mm, "Impulsado por Desesoft — SurveySaaS")
