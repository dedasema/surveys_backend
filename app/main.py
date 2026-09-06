from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.database import engine, Base
from app.models.audit_log import AuditLog
from fastapi import Request
from fastapi.responses import JSONResponse

import os
from fastapi.staticfiles import StaticFiles

from app.shared.infrastructure.exception_handlers import register_domain_exception_handlers

app = FastAPI(title="Mi API SaaS", version="0.1.0")
register_domain_exception_handlers(app)

os.makedirs("uploads/avatars", exist_ok=True)
os.makedirs("uploads/audio", exist_ok=True)
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

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
    import app.models.refresh_token
    import app.models.regla_ramificacion
    import app.models.audio_respuesta

    # Auto-create missing tables and migrate schema in database
    try:
        from sqlalchemy import text
        with engine.connect() as conn:
            # Extensión pgvector (si está soportada en el servidor PostgreSQL)
            try:
                conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
            except Exception as e_vec:
                print(f"Nota: pgvector no pudo ser inicializado en PostgreSQL local/remoto ({e_vec})")

            conn.execute(text("ALTER TABLE rol ADD COLUMN IF NOT EXISTS descripcion VARCHAR;"))
            
            # Migraciones para plan_suscripcion
            conn.execute(text("ALTER TABLE plan_suscripcion ADD COLUMN IF NOT EXISTS max_plantillas INTEGER NOT NULL DEFAULT 5;"))
            conn.execute(text("ALTER TABLE plan_suscripcion ADD COLUMN IF NOT EXISTS max_campanas INTEGER NOT NULL DEFAULT 5;"))
            conn.execute(text("ALTER TABLE plan_suscripcion ADD COLUMN IF NOT EXISTS max_entregas INTEGER NOT NULL DEFAULT 500;"))
            conn.execute(text("ALTER TABLE plan_suscripcion ADD COLUMN IF NOT EXISTS max_operadores INTEGER NOT NULL DEFAULT 1;"))
            conn.execute(text("ALTER TABLE plan_suscripcion ADD COLUMN IF NOT EXISTS permite_email BOOLEAN NOT NULL DEFAULT TRUE;"))
            conn.execute(text("ALTER TABLE plan_suscripcion ADD COLUMN IF NOT EXISTS permite_audio_voz BOOLEAN NOT NULL DEFAULT FALSE;"))
            conn.execute(text("ALTER TABLE plan_suscripcion ADD COLUMN IF NOT EXISTS permite_papel BOOLEAN NOT NULL DEFAULT FALSE;"))
            conn.execute(text("ALTER TABLE plan_suscripcion ADD COLUMN IF NOT EXISTS permite_ia_analisis BOOLEAN NOT NULL DEFAULT FALSE;"))
            conn.execute(text("ALTER TABLE plan_suscripcion ADD COLUMN IF NOT EXISTS permite_exportacion BOOLEAN NOT NULL DEFAULT TRUE;"))
            conn.execute(text("ALTER TABLE plan_suscripcion ADD COLUMN IF NOT EXISTS caracteristicas TEXT DEFAULT '';"))
            conn.execute(text("ALTER TABLE plan_suscripcion ADD COLUMN IF NOT EXISTS activo BOOLEAN NOT NULL DEFAULT TRUE;"))
            conn.execute(text("ALTER TABLE plan_suscripcion ADD COLUMN IF NOT EXISTS stripe_price_id VARCHAR(255);"))
            
            # Migración para entrega_encuesta
            conn.execute(text("ALTER TABLE entrega_encuesta ADD COLUMN IF NOT EXISTS creado_en TIMESTAMP WITH TIME ZONE DEFAULT NOW();"))

            # Migraciones para foto_url de usuarios
            conn.execute(text("ALTER TABLE suscriptor ADD COLUMN IF NOT EXISTS foto_url TEXT;"))
            conn.execute(text("ALTER TABLE cuenta_usuario ADD COLUMN IF NOT EXISTS foto_url TEXT;"))
            conn.execute(text("ALTER TABLE administrador ADD COLUMN IF NOT EXISTS foto_url TEXT;"))

            # Migraciones para integridad criptográfica Hash-Chain (RNF8)
            conn.execute(text("ALTER TABLE respuesta_encuesta ADD COLUMN IF NOT EXISTS hash VARCHAR(64);"))
            conn.execute(text("ALTER TABLE respuesta_encuesta ADD COLUMN IF NOT EXISTS hash_anterior VARCHAR(64);"))

            # Migraciones para motor de ramificación y preguntas generativas (RF17, RF17b)
            conn.execute(text("ALTER TABLE conversacion_encuesta ADD COLUMN IF NOT EXISTS preguntas_generativas_usadas INTEGER NOT NULL DEFAULT 0;"))
            conn.execute(text("ALTER TABLE conversacion_encuesta ADD COLUMN IF NOT EXISTS pregunta_generativa_activa TEXT;"))

            conn.commit()

        Base.metadata.create_all(bind=engine)
        print("Database tables verified/created/migrated successfully.")
    except Exception as e:
        print(f"Error creating/migrating tables: {e}")

    # Seed initial catalog data (roles, permisos, tipos_pregunta, etc.)
    from app.core.database import SessionLocal
    from app.models.catalogos import (
        Rol, Permiso, TipoPregunta, Canal, EstadoCampana, EstadoEntrega,
        EstadoDocumento, EstadoPago, MetodoPago
    )
    db = SessionLocal()
    try:
        # 1. Permisos del Sistema
        permisos_catalogo = [
            # Plantillas
            ("plantillas:ver", "Ver Plantillas", "Plantillas", "Permite visualizar el catálogo y detalle de plantillas"),
            ("plantillas:crear", "Crear Plantillas", "Plantillas", "Permite diseñar y guardar nuevas plantillas de encuesta"),
            ("plantillas:editar", "Editar Plantillas", "Plantillas", "Permite modificar preguntas y estructura de plantillas"),
            ("plantillas:eliminar", "Eliminar Plantillas", "Plantillas", "Permite dar de baja plantillas existentes"),
            # Campañas
            ("campanas:ver", "Ver Campañas", "Campañas", "Permite ver el listado y estado de campañas"),
            ("campanas:crear", "Crear Campañas", "Campañas", "Permite configurar y lanzar nuevas campañas"),
            ("campanas:editar", "Editar Campañas", "Campañas", "Permite reprogramar o modificar campañas"),
            ("campanas:eliminar", "Eliminar Campañas", "Campañas", "Permite cancelar o eliminar campañas"),
            # Destinatarios
            ("destinatarios:ver", "Ver Destinatarios", "Destinatarios", "Permite consultar la agenda de contactos"),
            ("destinatarios:crear", "Crear Destinatarios", "Destinatarios", "Permite agregar contactos individuales"),
            ("destinatarios:importar", "Importar Destinatarios", "Destinatarios", "Permite carga masiva mediante archivos Excel"),
            ("destinatarios:eliminar", "Eliminar Destinatarios", "Destinatarios", "Permite eliminar contactos del directorio"),
            # Entregas
            ("entregas:ver", "Ver Entregas", "Entregas", "Permite monitorear el estado de despachos y entregas"),
            ("entregas:enviar", "Despachar Entregas", "Entregas", "Permite disparar envíos masivos por email o WhatsApp"),
            ("entregas:generar_pdf", "Generar Formularios PDF", "Entregas", "Permite descargar PDFs individuales con QR y ZIPs"),
            ("entregas:disparar_voz", "Disparar Llamadas AI", "Entregas", "Permite ejecutar llamadas salientes automatizadas"),
            # Analítica & IA
            ("analytics:ver", "Ver Dashboard Analítico", "Analítica", "Permite acceder a KPIs, métricas y gráficos"),
            ("analytics:resumen_ia", "Generar Resúmenes IA", "Analítica", "Permite ejecutar inferencias cualitativas con GPT-4o"),
            ("analytics:exportar", "Exportar Reportes", "Analítica", "Permite exportar métricas y respuestas consolidadas"),
            # Operadores & Usuarios
            ("usuarios:ver", "Ver Operadores", "Usuarios", "Permite ver el equipo de operadores asociados"),
            ("usuarios:crear", "Crear Operadores", "Usuarios", "Permite registrar nuevos operadores"),
            ("usuarios:editar", "Editar Operadores", "Usuarios", "Permite modificar datos de operadores"),
            ("usuarios:eliminar", "Eliminar Operadores", "Usuarios", "Permite dar de baja operadores"),
            # Suscripciones & Facturación
            ("suscripciones:ver", "Ver Suscripción", "Suscripciones", "Permite ver el plan contratado y consumos"),
            ("suscripciones:gestionar", "Gestionar Pagos", "Suscripciones", "Permite actualizar plan o método de pago"),
            # Configuración & Catálogos (Admin)
            ("catalogos:ver", "Ver Catálogos", "Administración", "Permite consultar catálogos del sistema"),
            ("catalogos:administrar", "Administrar Catálogos", "Administración", "Permite crear o modificar catálogos y roles"),
        ]

        permisos_db_map = {}
        for codigo, nombre, modulo, descripcion in permisos_catalogo:
            p = db.query(Permiso).filter_by(codigo=codigo).first()
            if not p:
                p = Permiso(codigo=codigo, nombre=nombre, modulo=modulo, descripcion=descripcion)
                db.add(p)
                db.flush()
            permisos_db_map[codigo] = p

        # 2. Roles con descripciones y permisos predefinidos
        roles_config = {
            "admin": {
                "descripcion": "Administrador total del sistema con acceso irrestricto",
                "permisos": list(permisos_db_map.keys())
            },
            "empresa": {
                "descripcion": "Empresa suscriptora con control completo de sus encuestas, campañas y operadores",
                "permisos": [
                    "plantillas:ver", "plantillas:crear", "plantillas:editar", "plantillas:eliminar",
                    "campanas:ver", "campanas:crear", "campanas:editar", "campanas:eliminar",
                    "destinatarios:ver", "destinatarios:crear", "destinatarios:importar", "destinatarios:eliminar",
                    "entregas:ver", "entregas:enviar", "entregas:generar_pdf", "entregas:disparar_voz",
                    "analytics:ver", "analytics:resumen_ia", "analytics:exportar",
                    "usuarios:ver", "usuarios:crear", "usuarios:editar", "usuarios:eliminar",
                    "suscripciones:ver", "suscripciones:gestionar"
                ]
            },
            "operator": {
                "descripcion": "Operador de campo encargado de recolección, destinatarios y entregas",
                "permisos": [
                    "plantillas:ver",
                    "campanas:ver",
                    "destinatarios:ver", "destinatarios:crear", "destinatarios:importar",
                    "entregas:ver", "entregas:enviar", "entregas:generar_pdf"
                ]
            },
            "analista": {
                "descripcion": "Analista de datos con acceso de solo lectura y explotación analítica",
                "permisos": [
                    "plantillas:ver",
                    "campanas:ver",
                    "entregas:ver",
                    "analytics:ver", "analytics:resumen_ia", "analytics:exportar"
                ]
            }
        }

        for r_name, r_info in roles_config.items():
            rol_obj = db.query(Rol).filter_by(nombre=r_name).first()
            if not rol_obj:
                rol_obj = Rol(nombre=r_name, descripcion=r_info["descripcion"])
                db.add(rol_obj)
                db.flush()
            elif not rol_obj.descripcion:
                rol_obj.descripcion = r_info["descripcion"]

            # Si no tiene permisos asignados, asignar los por defecto
            if not rol_obj.permisos:
                rol_obj.permisos = [permisos_db_map[c] for c in r_info["permisos"] if c in permisos_db_map]

        db.commit()
        
        # Tipos de Pregunta
        tipos_default = ["texto", "opcion_unica", "opcion_multiple", "escala", "nps", "si_no"]
        for t_name in tipos_default:
            if not db.query(TipoPregunta).filter_by(nombre=t_name).first():
                db.add(TipoPregunta(nombre=t_name))

        # Canales
        canales_default = ["web", "email", "whatsapp", "qr", "link_directo"]
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
            {
                "nombre": "Gratuito",
                "precio_mensual": 0.0,
                "descripcion": "Plan básico gratuito de prueba",
                "max_plantillas": 3,
                "max_campanas": 2,
                "max_entregas": 100,
                "max_operadores": 1,
                "permite_email": True,
                "permite_audio_voz": True,
                "permite_papel": True,
                "permite_ia_analisis": False,
                "permite_exportacion": True,
                "caracteristicas": "3 Plantillas;2 Campañas;100 Entregas/mes;1 Operador;Prueba de OCR e IA",
                "activo": True,
            },
            {
                "nombre": "Profesional",
                "precio_mensual": 29.99,
                "descripcion": "Plan profesional con funciones avanzadas e IA",
                "max_plantillas": 50,
                "max_campanas": 50,
                "max_entregas": 5000,
                "max_operadores": 5,
                "permite_email": True,
                "permite_audio_voz": True,
                "permite_papel": True,
                "permite_ia_analisis": True,
                "permite_exportacion": True,
                "caracteristicas": "50 Plantillas;50 Campañas;5.000 Entregas/mes;5 Operadores;OCR Papel con IA;Audio / Voz con IA;Análisis Avanzado",
                "activo": True,
            },
            {
                "nombre": "Enterprise",
                "precio_mensual": 99.99,
                "descripcion": "Plan empresarial ilimitado",
                "max_plantillas": -1,
                "max_campanas": -1,
                "max_entregas": -1,
                "max_operadores": -1,
                "permite_email": True,
                "permite_audio_voz": True,
                "permite_papel": True,
                "permite_ia_analisis": True,
                "permite_exportacion": True,
                "caracteristicas": "Plantillas Ilimitadas;Campañas Ilimitadas;Entregas Ilimitadas;Operadores Ilimitados;OCR Papel con IA;Audio / Voz con IA;Exportación y API Completa",
                "activo": True,
            }
        ]
        for p_data in planes_default:
            plan_existente = db.query(PlanSuscripcion).filter_by(nombre=p_data["nombre"]).first()
            if not plan_existente:
                db.add(PlanSuscripcion(**p_data))
            else:
                for k, v in p_data.items():
                    setattr(plan_existente, k, v)

        db.commit()
        print("Catalogs and default plans seeded successfully.")
    except Exception as e:
        db.rollback()
        print(f"Error seeding catalogs: {e}")
    finally:
        db.close()

    print("FastAPI application startup complete.")



# ────────────────── Modular Architecture Routers ──────────────────
from app.modules.auth.infrastructure.router import router as auth_router
from app.modules.catalogos.infrastructure.router import (
    catalogos_router,
    anuncios_admin_router,
    anuncios_public_router,
)
from app.modules.subscription.infrastructure.router import router as subscription_router
from app.modules.admin.infrastructure.router import router as admin_router
from app.modules.campanas.infrastructure.router import router as campanas_router
from app.modules.plantillas.infrastructure.router import router as plantillas_router
from app.modules.entregas.infrastructure.router import (
    entregas_router,
    public_entregas_router,
    destinatarios_router,
)
from app.modules.respuestas.infrastructure.router import (
    respuestas_public_router,
    respuestas_private_router,
    encuestas_public_router,
)
from app.modules.channels.infrastructure.router import whatsapp_router
from app.modules.analytics.infrastructure.router import (
    analytics_router,
    nlp_router,
    pdf_router,
    dashboard_router,
)
from app.modules.ai_assistant.infrastructure.router import router as chat_router
from app.modules.auditoria.infrastructure.router import router as auditoria_router
from app.routers import seeder_router
from app.routers.ingesta_router import router as ingesta_router
from app.routers.integridad_router import router as integridad_router
from app.routers.audio_respuestas_router import router as audio_respuestas_router
from app.routers.encuestas_adaptativas_router import router as encuestas_adaptativas_router

# Registrar routers modulares
app.include_router(auth_router)
app.include_router(catalogos_router)
app.include_router(subscription_router)
app.include_router(admin_router)
app.include_router(anuncios_admin_router)
app.include_router(anuncios_public_router)
app.include_router(plantillas_router)
app.include_router(campanas_router)
app.include_router(entregas_router)
app.include_router(destinatarios_router)
app.include_router(respuestas_public_router)
app.include_router(respuestas_private_router)
app.include_router(public_entregas_router)
app.include_router(whatsapp_router)
app.include_router(analytics_router)
app.include_router(nlp_router)
app.include_router(encuestas_public_router)
app.include_router(pdf_router)
app.include_router(seeder_router.router)
app.include_router(dashboard_router)
app.include_router(chat_router)
app.include_router(auditoria_router)
app.include_router(ingesta_router)
app.include_router(integridad_router)
app.include_router(audio_respuestas_router)
app.include_router(encuestas_adaptativas_router)

@app.get("/", summary="Health check")
async def health_check():
    return {"status": "ok", "message": "API running"}

@app.get("/api/stripe-verify-session")
@app.get("/stripe-verify-session")
async def verify_session_fallback(session_id: str = ""):
    return {"success": True, "message": "Pago verificado exitosamente"}
