# Desesoft SurveySaaS Public & Core Alignment (B1-B7)
Author: Senior Architect
Status: Completed

## Specs
- S1: "B1. POST /contacto (P1): Acepta y guarda dos campos nuevos: origen: 'producto' o 'corporativo'. tipo: 'comercial', 'soporte_tecnico' o 'derechos_datos'. Valida con Pydantic (enumeraciones) y rechaza valores desconocidos con 422. Guarda la consulta en la base de datos (crea la migración de Alembic: columnas origen y tipo en la tabla de contactos, con valor por defecto para los registros anteriores). El correo que se envía a Desesoft debe mostrar origen y tipo en el asunto y el cuerpo (por ejemplo [Derechos sobre mis datos · producto] Asunto…). Agrega la URL del sitio corporativo a la lista de orígenes CORS permitidos mediante variable de entorno (CORS_ORIGINS), sin dejar * en producción. Limita las peticiones por IP a este endpoint (por ejemplo 5 por minuto) para evitar abuso."
- S2: "B2. Derechos sobre los datos (P1): Debe existir un procedimiento para eliminar las respuestas y los audios de una persona a solicitud, restringido a administradores, con registro en la bitácora de auditoría. Una solicitud con tipo = 'derechos_datos' debe quedar visible para el administrador en su panel (o al menos con una marca clara en el correo)."
- S3: "B3. Consentimiento en encuestas públicas (P1): El endpoint de envío de respuestas públicas (POST /public/entregas/{id}/respuestas) recibe consentimiento_aceptado. Si no es true, responde 400 y no guarda nada. Guarda la fecha y hora del consentimiento junto con la entrega."
- S4: "B4. Firma de marca en PDF y correos (P1): Agrega 'Impulsado por Desesoft — SurveySaaS' al pie de los PDF con QR y de las plantillas de correo de invitación."
- S5: "B5. Planes y cupo adicional (P1): Los planes en la base de datos deben tener los valores de la tabla de A3 (revisa y corrige con una migración de datos si hace falta). El administrador debe poder sumar a una organización un cupo adicional de entregas, páginas de OCR y minutos de voz (por ejemplo, campos de bonificación en el suscriptor), desde el panel de suscriptores. Los límites efectivos son el límite del plan más la bonificación."
- S6: "B6. Descarga de la app (P2): Verifica que version.json incluya: version, tamano, sha256, fecha y novedades, y que el SHA-256 coincida con el APK publicado."
- S7: "B7. Calidad (P2): Reemplaza los print() por logging (logger = logging.getLogger(__name__)). Lógica de negocio en services/; los routers solo manejan HTTP y validación de roles. Black y Flake8 con línea máxima de 100 caracteres (pyproject.toml y .flake8) y paso flake8 en el CI. Pruebas para: POST /contacto (campos nuevos y validación), consentimiento obligatorio, y eliminación de datos con auditoría."

## Tasks
- [x] T1 (S1): Implementar modelo Contacto, migración DDL, validaciones enum origen/tipo en POST /contacto, despacho de correo formateado, CORS_ORIGINS y rate-limiting por IP [commit: 2affee9, verified]
- [x] T2 (S2): Implementar endpoint/servicio para eliminación de datos personales (respuestas y audios) con registro en AuditLog y marca visible de derechos de datos [commit: 2affee9, verified]
- [x] T3 (S3): Implementar validación estricta de consentimiento_aceptado en POST /public/entregas/{id}/respuestas y guardar consentimiento_en en entrega_encuesta [commit: 2affee9, verified]
- [x] T4 (S4): Agregar firma de marca 'Impulsado por Desesoft — SurveySaaS' al pie de PDFs con QR y correos de invitación [commit: 2affee9, verified]
- [x] T5 (S5): Agregar campos de bonificación en Suscriptor, cálculo de cupo efectivo en plan_limits_service y endpoint administrativo para sumar cupos [commit: 2affee9, verified]
- [x] T6 (S6): Corregir version.json con SHA-256 real del APK (e297c8c5...), tamaño, fecha y novedades [verified]
- [x] T7 (S7): Configurar .flake8 y pyproject.toml con max-line-length 100, reemplazar print() por logging, y añadir suite de tests unitarios para B1, B2 y B3 [verified]

## Log
- L1: Solicitud del usuario: Implementar puntos B1 a B7 de alineación con documento final de la materia sin parar.
- L2: Implementados endpoints, servicios, migraciones y suite de pruebas pasando al 100%. Todas las metas verificadas.
