import os
from typing import Optional
import boto3
from botocore.exceptions import ClientError
from fastapi import UploadFile, HTTPException

from app.core.config import settings

def is_s3_configured() -> bool:
    """
    Checks if AWS S3 credentials and bucket name are configured and non-empty.
    """
    bucket = (settings.AWS_S3_BUCKET_NAME or os.getenv("AWS_S3_BUCKET_NAME") or "").strip()
    key_id = (settings.AWS_ACCESS_KEY_ID or os.getenv("AWS_ACCESS_KEY_ID") or "").strip()
    secret_key = (settings.AWS_SECRET_ACCESS_KEY or os.getenv("AWS_SECRET_ACCESS_KEY") or "").strip()
    return bool(bucket and key_id and secret_key)

def get_s3_client():
    aws_access_key = (settings.AWS_ACCESS_KEY_ID or os.getenv("AWS_ACCESS_KEY_ID") or "").strip()
    aws_secret_key = (settings.AWS_SECRET_ACCESS_KEY or os.getenv("AWS_SECRET_ACCESS_KEY") or "").strip()
    aws_region = (settings.AWS_REGION or os.getenv("AWS_REGION") or "us-east-1").strip()
    return boto3.client(
        "s3",
        aws_access_key_id=aws_access_key,
        aws_secret_access_key=aws_secret_key,
        region_name=aws_region,
    )

async def upload_file_to_s3(file: UploadFile, s3_key: str) -> str:
    """
    Uploads a file to Amazon S3 and returns the public permanent URL.
    """
    bucket = (settings.AWS_S3_BUCKET_NAME or os.getenv("AWS_S3_BUCKET_NAME") or "").strip()
    region = (settings.AWS_REGION or os.getenv("AWS_REGION") or "us-east-1").strip()
    custom_domain = (settings.AWS_S3_CUSTOM_DOMAIN or os.getenv("AWS_S3_CUSTOM_DOMAIN") or "").strip()

    if not is_s3_configured():
        raise RuntimeError("AWS S3 is not configured. Missing credentials or AWS_S3_BUCKET_NAME.")

    try:
        content_type = file.content_type or "application/octet-stream"
        file.file.seek(0)
        s3 = get_s3_client()
        s3.upload_fileobj(
            file.file,
            bucket,
            s3_key,
            ExtraArgs={"ContentType": content_type}
        )
        if custom_domain:
            return f"https://{custom_domain.rstrip('/')}/{s3_key}"
        return f"https://{bucket}.s3.{region}.amazonaws.com/{s3_key}"
    except ClientError as e:
        raise HTTPException(status_code=500, detail=f"Error al persistir archivo en S3: {str(e)}")
