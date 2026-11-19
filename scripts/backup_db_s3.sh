#!/usr/bin/env bash
set -eo pipefail

BACKUP_DIR="/home/ubuntu/backups"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_FILE="${BACKUP_DIR}/surveys_db_${TIMESTAMP}.sql.gz"
S3_BUCKET="s3://surveys-backend-db-backups-2026/backups"

mkdir -p "$BACKUP_DIR"

echo "[$(date)] Iniciando backup de PostgreSQL surveys_db..."
sudo docker exec surveys_db pg_dump -U postgres -d surveys_db | gzip > "$BACKUP_FILE"

FILE_SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
echo "[$(date)] Backup generado: $BACKUP_FILE ($FILE_SIZE)"

echo "[$(date)] Subiendo a Amazon S3 ($S3_BUCKET)..."
if [ -f "/home/ubuntu/surveys_backend/.env" ]; then
    export AWS_ACCESS_KEY_ID=$(grep -E '^AWS_ACCESS_KEY_ID=' /home/ubuntu/surveys_backend/.env | cut -d '=' -f2- | tr -d '"\r ')
    export AWS_SECRET_ACCESS_KEY=$(grep -E '^AWS_SECRET_ACCESS_KEY=' /home/ubuntu/surveys_backend/.env | cut -d '=' -f2- | tr -d '"\r ')
    export AWS_DEFAULT_REGION="us-east-1"
fi

aws s3 cp "$BACKUP_FILE" "${S3_BUCKET}/surveys_db_${TIMESTAMP}.sql.gz"

echo "[$(date)] Respaldo cargado a S3 con éxito."

# Limpiar archivos locales con más de 3 días para proteger el disco EBS
find "$BACKUP_DIR" -type f -name "surveys_db_*.sql.gz" -mtime +3 -delete
echo "[$(date)] Proceso de backup finalizado correctamente."
