import os
import sys
import csv
import boto3
from pathlib import Path
from botocore.exceptions import ClientError

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
    if not access_key or not secret_key:
        print("Error: Credenciales no encontradas.")
        sys.exit(1)

    s3 = boto3.client(
        "s3",
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name=REGION
    )

    print(f"1. Verificando o creando bucket S3: {BUCKET_NAME}...")
    try:
        # En us-east-1 no se pasa CreateBucketConfiguration
        s3.create_bucket(Bucket=BUCKET_NAME)
        print(f"Bucket '{BUCKET_NAME}' creado exitosamente.")
    except ClientError as e:
        code = e.response.get("Error", {}).get("Code")
        if code in ("BucketAlreadyOwnedByYou", "BucketAlreadyExists"):
            print(f"Bucket '{BUCKET_NAME}' ya existe.")
        else:
            print(f"Error al crear bucket: {e}")
            sys.exit(1)

    print("2. Configurando regla de ciclo de vida (Lifecycle): Retención de 14 días...")
    lifecycle_config = {
        "Rules": [
            {
                "ID": "DeleteBackupsAfter14Days",
                "Status": "Enabled",
                "Filter": {
                    "Prefix": "backups/"
                },
                "Expiration": {
                    "Days": 14
                }
            }
        ]
    }

    s3.put_bucket_lifecycle_configuration(
        Bucket=BUCKET_NAME,
        LifecycleConfiguration=lifecycle_config
    )
    print("Regla de ciclo de vida de 14 días aplicada correctamente.")

    # Verificar regla
    current_lifecycle = s3.get_bucket_lifecycle_configuration(Bucket=BUCKET_NAME)
    print("Reglas activas:", current_lifecycle.get("Rules"))

if __name__ == "__main__":
    main()
