import uuid
import random
from datetime import datetime, timedelta, timezone
from sqlalchemy import text
from app.core.database import SessionLocal, engine
from app.core.security import hash_password
from app.models.catalogos import Rol, TipoPregunta, Canal, EstadoCampana, EstadoEntrega
from app.models.subscription import PlanSuscripcion, SuscripcionSuscriptor
from app.models.administrador import Administrador
from app.models.suscriptor import Suscriptor
from app.models.cuenta_usuario import CuentaUsuario
from app.models.survey import (
    PlantillaEncuesta, PreguntaEncuesta, OpcionEncuesta,
    CampanaEncuesta, Destinatario, EntregaEncuesta, RespuestaEncuesta, RespuestaPregunta
)
from app.services.hash_chain_service import vincular_hash_cadena

def seed_clean_and_populate():
    db = SessionLocal()
    print("1. Limpiando tablas transaccionales de la base de datos...")
    with engine.connect() as conn:
        conn.execute(text("TRUNCATE suscriptor, administrador, cuenta_usuario CASCADE;"))
        conn.commit()
    print("Tablas transaccionales limpiadas exitosamente.")

    # Mapeo dinamico de catalogos para evitar inconsistencias de IDs
    rol_admin = db.query(Rol).filter_by(nombre="admin").first().id
    rol_empresa = db.query(Rol).filter_by(nombre="empresa").first().id
    rol_operator = db.query(Rol).filter_by(nombre="operator").first().id

    tipo_texto = db.query(TipoPregunta).filter_by(nombre="texto").first().id
    tipo_opcion_unica = db.query(TipoPregunta).filter_by(nombre="opcion_unica").first().id
    tipo_escala = db.query(TipoPregunta).filter_by(nombre="escala").first().id
    tipo_si_no = db.query(TipoPregunta).filter_by(nombre="si_no").first().id

    canal_web = db.query(Canal).filter_by(nombre="web").first().id
    canal_email = db.query(Canal).filter_by(nombre="email").first().id
    canal_qr = db.query(Canal).filter_by(nombre="qr").first().id

    estado_camp_activa = db.query(EstadoCampana).filter_by(nombre="activa").first().id
    estado_camp_finalizada = db.query(EstadoCampana).filter_by(nombre="finalizada").first().id

    estado_ent_respondido = db.query(EstadoEntrega).filter_by(nombre="respondido").first().id
    estado_ent_enviado = db.query(EstadoEntrega).filter_by(nombre="enviado").first().id

    plan_pro = db.query(PlanSuscripcion).filter_by(nombre="Profesional").first() or db.query(PlanSuscripcion).first()

    print("2. Creando usuario Administrador y Empresas (Suscriptores)...")
    # 1. Superadmin
    admin = Administrador(
        id=uuid.uuid4(),
        email="admin@admin.com",
        password_hash=hash_password("admin123"),
        rol_id=rol_admin,
        activo=True
    )
    db.add(admin)

    # 2. Empresas
    empresas_data = [
        {"nombre": "TechCorp Solutions", "email": "demo@empresa.com", "tel": "+59170011223"},
        {"nombre": "InnovateSoft Latam", "email": "contacto@innovatesoft.com", "tel": "+59171122334"},
        {"nombre": "Digital Dynamics", "email": "ventas@digitaldynamics.com", "tel": "+59172233445"}
    ]

    suscriptores = []
    for emp in empresas_data:
        susc = Suscriptor(
            id=uuid.uuid4(),
            nombre=emp["nombre"],
            email=emp["email"],
            telefono=emp["tel"],
            password_hash=hash_password("demo123"),
            rol_id=rol_empresa,
            estado="activo",
            foto_url=f"https://api.dicebear.com/7.x/identicon/svg?seed={emp['nombre'].replace(' ', '')}"
        )
        db.add(susc)
        db.flush()

        # Asignar suscripcion activa
        suscripcion = SuscripcionSuscriptor(
            id=uuid.uuid4(),
            suscriptor_id=susc.id,
            plan_id=plan_pro.id,
            estado="activa",
            inicia_en=datetime.now(timezone.utc) - timedelta(days=30),
            expira_en=datetime.now(timezone.utc) + timedelta(days=335)
        )
        db.add(suscripcion)
        suscriptores.append(susc)

        # 3. Operadores por empresa
        for i in range(1, 3):
            op = CuentaUsuario(
                id=uuid.uuid4(),
                suscriptor_id=susc.id,
                email=f"operador{i}@{emp['email'].split('@')[1]}",
                password_hash=hash_password("operator123"),
                nombre_completo=f"Operador {i} {emp['nombre']}",
                rol_id=rol_operator,
                activo=True
            )
            db.add(op)

    db.commit()
    print(f"Creados 1 admin y {len(suscriptores)} empresas con sus operadores y suscripciones.")

    print("3. Creando Plantillas, Preguntas, Campañas y Respuestas realistas...")
    # Plantillas para la empresa principal (TechCorp Solutions)
    susc_principal = suscriptores[0]

    plantillas_def = [
        {
            "nombre": "Satisfacción de Servicio y Atención 2026",
            "descripcion": "Encuesta periódica para evaluar la calidad del servicio, tiempos de respuesta y atención técnica.",
            "preguntas": [
                {"texto": "¿Cómo calificaría la calidad general de nuestro servicio?", "tipo": tipo_escala, "opciones": ["1", "2", "3", "4", "5"]},
                {"texto": "¿El personal resolvió su requerimiento en el tiempo esperado?", "tipo": tipo_si_no, "opciones": ["Sí", "No"]},
                {"texto": "¿Cuál de los siguientes aspectos considera más valioso?", "tipo": tipo_opcion_unica, "opciones": ["Velocidad de respuesta", "Atención cordial", "Precisión técnica", "Facilidad de uso"]},
                {"texto": "¿Tiene algún comentario o sugerencia de mejora para nuestro equipo?", "tipo": tipo_texto, "opciones": []}
            ]
        },
        {
            "nombre": "Evaluación de Producto y Experiencia de Usuario",
            "descripcion": "Medición del Net Promoter Score (NPS) y usabilidad de la plataforma digital.",
            "preguntas": [
                {"texto": "¿Qué tan probable es que recomiende nuestra plataforma a un colega?", "tipo": tipo_escala, "opciones": ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10"]},
                {"texto": "¿La navegación por el sistema le resultó intuitiva?", "tipo": tipo_si_no, "opciones": ["Sí", "No"]},
                {"texto": "¿Qué módulo o funcionalidad utiliza con mayor frecuencia?", "tipo": tipo_opcion_unica, "opciones": ["Creación de encuestas", "Analítica y reportes", "Gestión de canales", "Copilot IA"]},
                {"texto": "¿Qué característica nueva le gustaría ver en la próxima versión?", "tipo": tipo_texto, "opciones": []}
            ]
        }
    ]

    for p_info in plantillas_def:
        plantilla = PlantillaEncuesta(
            id=uuid.uuid4(),
            suscriptor_id=susc_principal.id,
            nombre=p_info["nombre"],
            descripcion=p_info["descripcion"],
            activo=True
        )
        db.add(plantilla)
        db.flush()

        preguntas_creadas = []
        for orden, preg in enumerate(p_info["preguntas"], start=1):
            pregunta = PreguntaEncuesta(
                id=uuid.uuid4(),
                plantilla_id=plantilla.id,
                orden=orden,
                texto=preg["texto"],
                tipo_pregunta_id=preg["tipo"],
                obligatorio=True
            )
            db.add(pregunta)
            db.flush()

            opciones_creadas = []
            for val, op_txt in enumerate(preg["opciones"], start=1):
                opcion = OpcionEncuesta(
                    id=uuid.uuid4(),
                    pregunta_id=pregunta.id,
                    texto=op_txt,
                    valor=str(val)
                )
                db.add(opcion)
                opciones_creadas.append(opcion)

            preguntas_creadas.append({"obj": pregunta, "opciones": opciones_creadas})

        # Crear 2 Campañas por plantilla
        for c_idx, c_nombre in enumerate(["Campaña Feedback Q4", "Campaña Clientes Estratégicos"], start=1):
            campana = CampanaEncuesta(
                id=uuid.uuid4(),
                suscriptor_id=susc_principal.id,
                plantilla_id=plantilla.id,
                nombre=f"{c_nombre} - {plantilla.nombre[:30]}",
                canal_id=canal_email if c_idx == 1 else canal_web,
                programada_en=datetime.now(timezone.utc) - timedelta(days=15 * c_idx),
                estado_id=estado_camp_activa if c_idx == 1 else estado_camp_finalizada
            )
            db.add(campana)
            db.flush()

            # Crear 5 Destinatarios y Entregas con respuestas para esta campaña
            clientes_muestra = [
                ("Carlos Mendoza", "carlos.mendoza@gmail.com", "+59178899001"),
                ("Mariana Rios", "mariana.rios@outlook.com", "+59178899002"),
                ("Rodrigo Silva", "rodrigo.silva@empresa.bo", "+59178899003"),
                ("Luciana Vargas", "luciana.vargas@empresa.bo", "+59178899004"),
                ("Fernando Gutierrez", "fernando.g@gmail.com", "+59178899005"),
            ]

            for c_nom, c_mail, c_tel in clientes_muestra:
                dest = Destinatario(
                    id=uuid.uuid4(),
                    suscriptor_id=susc_principal.id,
                    nombre=c_nom,
                    email=c_mail,
                    telefono=c_tel,
                    creado_en=datetime.now(timezone.utc)
                )
                db.add(dest)
                db.flush()

                entrega = EntregaEncuesta(
                    id=uuid.uuid4(),
                    campana_id=campana.id,
                    destinatario_id=dest.id,
                    estado_id=estado_ent_respondido,
                    canal_id=campana.canal_id,
                    enviado_en=datetime.now(timezone.utc) - timedelta(days=random.randint(2, 10)),
                    respondido_en=datetime.now(timezone.utc) - timedelta(hours=random.randint(1, 48))
                )
                db.add(entrega)
                db.flush()

                # Respuesta de Encuesta (con vinculacion Hash-Chain)
                resp_enc = RespuestaEncuesta(
                    id=uuid.uuid4(),
                    entrega_id=entrega.id,
                    recibido_en=entrega.respondido_en,
                    puntuacion=round(random.uniform(4.0, 5.0), 2),
                    raw_payload={"cliente": c_nom, "campana": campana.nombre}
                )
                db.add(resp_enc)
                db.flush()

                # Vincular criptográficamente en Hash-Chain (RNF8)
                vincular_hash_cadena(db, resp_enc)

                # Respuestas a cada pregunta
                for preg_item in preguntas_creadas:
                    p_obj = preg_item["obj"]
                    ops = preg_item["opciones"]

                    if ops:
                        op_sel = random.choice(ops)
                        rp = RespuestaPregunta(
                            id=uuid.uuid4(),
                            respuesta_id=resp_enc.id,
                            pregunta_id=p_obj.id,
                            opcion_id=op_sel.id,
                            texto=op_sel.texto,
                            numero=float(op_sel.valor) if op_sel.valor and op_sel.valor.isdigit() else None
                        )
                    else:
                        comentarios = [
                            "Excelente servicio y muy atentos en la resolución.",
                            "Todo bien, me gustaría que agreguen soporte nocturno.",
                            "La plataforma es muy rápida y cómoda de usar.",
                            "Buen soporte, cumplieron con los tiempos acordados."
                        ]
                        rp = RespuestaPregunta(
                            id=uuid.uuid4(),
                            respuesta_id=resp_enc.id,
                            pregunta_id=p_obj.id,
                            texto=random.choice(comentarios)
                        )
                    db.add(rp)

    db.commit()
    db.close()
    print("4. ¡Seeding masivo realista completado con éxito!")

if __name__ == "__main__":
    seed_clean_and_populate()
