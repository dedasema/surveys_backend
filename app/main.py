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
#from app.routers import nlp_router
from app.routers import encuestas_router
from app.routers import seeder_router
from app.routers import pdf_router
from app.routers import dashboard_router
from app.routers import chat_router

from fastapi import Request
from fastapi.responses import JSONResponse

app = FastAPI(title="Mi API SaaS", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  
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
    from app.models.catalogos import Rol, TipoPregunta, Canal, EstadoCampana, EstadoEntrega
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

        db.commit()
        print("Catalogs seeded successfully.")
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
#app.include_router(nlp_router.router)
app.include_router(encuestas_router.router)
app.include_router(pdf_router.router)
app.include_router(seeder_router.router)
app.include_router(dashboard_router.router)
app.include_router(chat_router.router)

@app.get("/", summary="Health check")
async def health_check():
    return {"status": "ok", "message": "API running"}
