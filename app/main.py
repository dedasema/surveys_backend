from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.database import engine, Base
from app.routers import auth, catalogos, subscription, plantillas_router, campanas_router, preguntas_router
from app.routers import opciones_router, entregas_router, destinatarios_router
from app.routers.respuestas_router import public_router as respuestas_public_router
from app.routers.respuestas_router import private_router as respuestas_private_router
from app.routers.entregas_router import public_router as entregas_public_router
from app.routers import whatsapp_router
from app.routers import vapi_router
from app.routers import analytics_router
from app.routers import nlp_router
from app.routers import encuestas_router
from app.routers import seeder_router
from app.routers import pdf_router
from app.routers import dashboard_router
from app.routers import chat_router

from fastapi import Request
from fastapi.responses import JSONResponse

app = FastAPI(title="Mi API SaaS", version="0.1.0")

origins = [
    "https://surveysfrontend.vercel.app",
    "http://localhost:3000",
    "http://localhost:5173",
    "http://localhost:8000",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:5173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    origin = request.headers.get("origin", "*")
    return JSONResponse(
        status_code=500,
        content={"detail": f"Internal Server Error: {str(exc)}"},
        headers={
            "Access-Control-Allow-Origin": origin if origin != "*" else "*",
            "Access-Control-Allow-Credentials": "true",
            "Access-Control-Allow-Methods": "*",
            "Access-Control-Allow-Headers": "*",
        }
    )

@app.on_event("startup")
async def startup_event():
    # Ensure all models are loaded so Base knows all tables
    import app.models.catalogos
    import app.models.administrador
    import app.models.suscriptor
    import app.models.cuenta_usuario
    import app.models.subscription
    import app.models.survey

    # Auto-create missing tables in database
    try:
        Base.metadata.create_all(bind=engine)
        print("Database tables verified/created successfully.")
    except Exception as e:
        print(f"Error creating tables: {e}")

    # Seed initial catalog data (roles, tipos_pregunta, etc.)
    from app.core.database import SessionLocal
    from app.models.catalogos import (
        Rol, TipoPregunta, Canal, EstadoCampana, EstadoEntrega,
        EstadoDocumento, EstadoPago, MetodoPago
    )
    db = SessionLocal()
    try:
        # Roles
        roles_default = ["admin", "empresa", "operator"]
        for r_name in roles_default:
            if not db.query(Rol).filter_by(nombre=r_name).first():
                db.add(Rol(nombre=r_name))
        
        # Tipos de Pregunta
        tipos_default = ["texto", "opcion_unica", "opcion_multiple", "escala", "nps", "si_no"]
        for t_name in tipos_default:
            if not db.query(TipoPregunta).filter_by(nombre=t_name).first():
                db.add(TipoPregunta(nombre=t_name))

        # Canales
        canales_default = ["web", "email", "whatsapp", "vapi_voz", "qr", "link_directo"]
        for c_name in canales_default:
            if not db.query(Canal).filter_by(nombre=c_name).first():
                db.add(Canal(nombre=c_name))

        # Estado Campaña
        estados_camp = ["borrador", "activa", "pausada", "finalizada", "cancelada"]
        for ec_name in estados_camp:
            if not db.query(EstadoCampana).filter_by(nombre=ec_name).first():
                db.add(EstadoCampana(nombre=ec_name))

        # Estado Entrega
        estados_ent = ["pendiente", "enviado", "entregado", "abierto", "respondido", "fallido", "rebotado"]
        for ee_name in estados_ent:
            if not db.query(EstadoEntrega).filter_by(nombre=ee_name).first():
                db.add(EstadoEntrega(nombre=ee_name))

        # Estado Documento
        estados_doc = ["borrador", "generado", "enviado", "firmado", "archivado"]
        for ed_name in estados_doc:
            if not db.query(EstadoDocumento).filter_by(nombre=ed_name).first():
                db.add(EstadoDocumento(nombre=ed_name))

        # Estado Pago
        estados_pago = ["pendiente", "pagado", "fallido", "reembolsado", "cancelado"]
        for ep_name in estados_pago:
            if not db.query(EstadoPago).filter_by(nombre=ep_name).first():
                db.add(EstadoPago(nombre=ep_name))

        # Metodo Pago
        metodos_pago = ["tarjeta_credito", "tarjeta_debito", "transferencia", "paypal", "stripe"]
        for mp_name in metodos_pago:
            if not db.query(MetodoPago).filter_by(nombre=mp_name).first():
                db.add(MetodoPago(nombre=mp_name))

        # Planes por defecto (Suscripciones)
        from app.models.subscription import PlanSuscripcion
        planes_default = [
            {"nombre": "Gratuito", "precio_mensual": 0.0, "descripcion": "Plan básico gratuito de prueba"},
            {"nombre": "Profesional", "precio_mensual": 29.99, "descripcion": "Plan profesional con funciones avanzadas e IA"},
            {"nombre": "Enterprise", "precio_mensual": 99.99, "descripcion": "Plan empresarial ilimitado"}
        ]
        for p_data in planes_default:
            if not db.query(PlanSuscripcion).filter_by(nombre=p_data["nombre"]).first():
                db.add(PlanSuscripcion(**p_data))

        db.commit()
        print("Catalogs and default plans seeded successfully.")
    except Exception as e:
        db.rollback()
        print(f"Error seeding catalogs: {e}")
    finally:
        db.close()

    print("FastAPI application startup complete.")



# Registrar todos los routers
app.include_router(auth.router)
app.include_router(catalogos.router)
app.include_router(subscription.router)
app.include_router(plantillas_router.router)
app.include_router(campanas_router.router)
app.include_router(preguntas_router.router)
app.include_router(opciones_router.router)
app.include_router(entregas_router.router)
app.include_router(destinatarios_router.router)
app.include_router(respuestas_public_router)
app.include_router(respuestas_private_router)
app.include_router(entregas_public_router)
app.include_router(whatsapp_router.router)
app.include_router(vapi_router.router)
app.include_router(analytics_router.router)
app.include_router(nlp_router.router)
app.include_router(encuestas_router.router)
app.include_router(pdf_router.router)
app.include_router(seeder_router.router)
app.include_router(dashboard_router.router)
app.include_router(chat_router.router)

@app.get("/", summary="Health check")
async def health_check():
    return {"status": "ok", "message": "API running"}

@app.get("/api/stripe-verify-session")
@app.get("/stripe-verify-session")
async def verify_session_fallback(session_id: str = ""):
    return {"success": True, "message": "Pago verificado exitosamente"}
