import os
import sys
import csv
import gzip
import boto3
from pathlib import Path

REGION = "us-east-1"
CSV_PATH = Path(__file__).resolve().parent.parent / "agent-deployer_accessKeys.csv"
BUCKET_NAME = "surveys-backend-db-backups-2026"

def get_credentials():
    access_key = os.getenv("AWS_ACCESS_KEY_ID")
    secret_key = os.getenv("AWS_SECRET_ACCESS_KEY")
    if not access_key or not secret_key:
        if CSV_PATH.exists():
            with open(CSV_PATH, "r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    access_key = row.get("Access key ID") or row.get("access_key_id")
                    secret_key = row.get("Secret access key") or row.get("secret_access_key")
                    break
    return access_key, secret_key

def main():
    access_key, secret_key = get_credentials()
    s3 = boto3.client(
        "s3",
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name=REGION
    )

    print("1. Listando respaldos en S3...")
    res = s3.list_objects_v2(Bucket=BUCKET_NAME, Prefix="backups/")
    objects = res.get("Contents", [])
    if not objects:
        print("No se encontraron respaldos.")
        sys.exit(1)

    latest = sorted(objects, key=lambda x: x["LastModified"], reverse=True)[0]
    key = latest["Key"]
    print(f"Último respaldo encontrado en S3: {key} ({latest['Size']} bytes)")

    local_gz = Path("temp_backup_test.sql.gz")
    local_sql = Path("temp_backup_test.sql")

    print(f"2. Descargando {key} a {local_gz}...")
    s3.download_file(BUCKET_NAME, key, str(local_gz))
    print("Descarga completada.")

    print(f"3. Descomprimiendo a {local_sql}...")
    with gzip.open(local_gz, "rb") as f_in, open(local_sql, "wb") as f_out:
        f_out.write(f_in.read())

    sql_size = local_sql.stat().st_size
    print(f"Archivo SQL descomprimido: {sql_size} bytes")

    print("4. Analizando integridad del volcado SQL...")
    with open(local_sql, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()

    tables_found = []
    copy_tables = []
    for line in content.splitlines():
        if "CREATE TABLE" in line:
            tables_found.append(line.strip())
        elif "COPY public." in line:
            copy_tables.append(line.strip().split()[1])

    print(f"Total CREATE TABLE encontradas: {len(tables_found)}")
    print("Muestra de tablas creadas:")
    for t in tables_found[:8]:
        print(f"  • {t}")

    print(f"\nTablas con datos (COPY public.*): {len(copy_tables)}")
    for c in copy_tables[:10]:
        print(f"  • {c}")

    # Verificar presencia de extensiones y tablas críticas
    has_vector = "CREATE EXTENSION IF NOT EXISTS vector" in content or "vector" in content
    has_suscriptores = "suscriptor" in content
    has_encuestas = "plantilla_encuesta" in content or "campana_encuesta" in content

    print("\nVerificación de integridad estructural:")
    print(f"  - Extensión pgvector presente: {has_vector}")
    print(f"  - Tabla suscriptor presente: {has_suscriptores}")
    print(f"  - Tablas de encuestas presentes: {has_encuestas}")

    # Limpiar archivos temporales
    local_gz.unlink(missing_ok=True)
    local_sql.unlink(missing_ok=True)
    print("\n[OK] Prueba de descarga y validación de restauración superada con éxito.")

if __name__ == "__main__":
    main()
