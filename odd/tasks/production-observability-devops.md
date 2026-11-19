# Production Observability, DevOps & Resilience
Author: Senior Architect
Status: Completed

## Specs
- S1: "Agregar flake8 y cobertura (pytest --cov) antes/junto con las pruebas" en requirements.txt y .github/workflows/ci.yml.
- S2: "Después del docker compose restart, el job de deploy debe hacer curl -f a GET / (con reintentos) y fallar si no responde. Que ese mismo paso consulte también /metrics".
- S3: "Añade tag al repositorio".
- S4: "Alarmas y SNS (P1): crear un tema SNS con tu correo y alarmas de CloudWatch para CPU, disco, StatusCheckFailed y errores 5xx".
- S5: "Chequeo de disponibilidad (P1): un monitor externo (por ejemplo UptimeRobot) sobre GET / con aviso al correo".
- S6: "Respaldos automáticos (P1): script con pg_dump ejecutado por cron cada día, subida a un bucket de S3 y borrado de respaldos con más de 14 días (regla de ciclo de vida de S3). Prueba una restauración en local y guarda captura".
- S7: "Sentry (P2): crear el proyectos frontend React e integrar el SDK con su DSN en .env/variables".
- S8: "Prometheus + Grafana (P3): agregar ambos servicios al compose (o a otra instancia), con /metrics como objetivo, y un tablero básico".

## Tasks
- [x] T1 (S1): Configurar flake8 y pytest-cov en requirements.txt y pipeline CI/CD [inline]
- [x] T2 (S2): Configurar verificación post-deploy con curl -f y reintentos para GET / y GET /metrics [inline]
- [x] T3 (S3): Crear y pushear tag versionado v1.0.0 al repositorio [inline]
- [x] T4 (S4): Crear tema SNS, suscribir correo dedasema734012@gmail.com y configurar alarmas CloudWatch en AWS [inline]
- [x] T5 (S5): Configurar monitor de disponibilidad externa para GET / [inline]
- [x] T6 (S6): Crear bucket S3 con ciclo de vida de 14 días, script de backup con pg_dump y cron, y ejecutar prueba de restauración [inline]
- [x] T7 (S7): Integrar SDK de Sentry en surveys_frontend con variables de entorno [inline]
- [x] T8 (S8): Configurar stack de Prometheus + Grafana en docker-compose con objetivo /metrics y datasource [inline]

## Log
- L1: Solicitud del usuario: Agregar flake8 y cobertura, chequeo post-deploy curl -f a / y /metrics, tag al repo, alarmas CloudWatch + SNS (P1), chequeo disponibilidad (P1), respaldos automáticos pg_dump + S3 14 días (P1), Sentry en frontend (P2), Prometheus + Grafana (P3).
- L2: Permisos de IAM AWS habilitados con éxito (AmazonSNSFullAccess, CloudWatchFullAccess, AmazonS3FullAccess).
- L3: Flake8 configurado y resueltos 21 falsos positivos y nombres no definidos (logger, datetime, HTTPException).
- L4: Cobertura ejecutada con pytest --cov: 112 tests pasaron exitosamente (54% de cobertura global).
- L5: CloudWatch y SNS creados en AWS us-east-1: tema surveys-backend-alerts con suscripción enviada a dedasema734012@gmail.com y 4 alarmas métricas (CPU, StatusCheckFailed, 5xx, Disk).
- L6: Bucket S3 surveys-backend-db-backups-2026 creado con regla de ciclo de vida de expiración a 14 días. Script de backup desplegado y probado en VPS con cron diario a las 03:00 UTC. Prueba de restauración local superada (39 tablas).
- L7: Sentry integrado en frontend React index.jsx con VITE_SENTRY_DSN en .env.example.
- L8: Stack de observabilidad Prometheus v2.50.0 + Grafana v10.4.0 configurado en docker-compose.yml con dashboard surveys_dashboard.json y datasource de Prometheus scrapeando /metrics cada 10s.
