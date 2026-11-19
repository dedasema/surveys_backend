from pydantic_settings import BaseSettings
from typing import Optional, Union
import os

class Settings(BaseSettings):
    DATABASE_URL: Union[str, None] = os.getenv(
        "DATABASE_URL", 
        "postgresql://postgres:postgres@localhost:5432/surveys_db"
    )
    SECRET_KEY: str = os.getenv("SECRET_KEY", "super_secret_default_key_2026")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    WHAPI_TOKEN: Optional[str] = ""
    WHAPI_API_URL: str = "https://gate.whapi.cloud"
    WHATSAPP_PHONE_ID: Optional[str] = ""
    WHATSAPP_TOKEN: Optional[str] = ""
    WHATSAPP_VERIFY_TOKEN: Optional[str] = "surveys_whatsapp_verify_token_2026"
    OPENAI_API_KEY: Optional[str] = ""
    GEMINI_API_KEY: Optional[str] = ""
    GEMINI_MODEL: str = "gemini-2.0-flash"
    API_BASE_URL: Optional[str] = "http://localhost:8000"
    STRIPE_SECRET_KEY: Optional[str] = ""
    STRIPE_PUBLIC_KEY: Optional[str] = ""
    STRIPE_WEBHOOK_SECRET: Optional[str] = ""
    FRONTEND_URL: str = os.getenv("FRONTEND_URL", "http://localhost:3000")
    SURVEY_LINK_EXPIRY_DAYS: int = 7
    SMTP_SERVER: Optional[str] = os.getenv("SMTP_SERVER", os.getenv("SMTP_HOST", "smtp.gmail.com"))
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", 587))
    SMTP_USERNAME: Optional[str] = os.getenv("SMTP_USERNAME", os.getenv("SMTP_USER", ""))
    SMTP_PASSWORD: Optional[str] = os.getenv("SMTP_PASSWORD", "")
    RESEND_API_KEY: Optional[str] = os.getenv("RESEND_API_KEY", "")
    BREVO_API_KEY: Optional[str] = os.getenv("BREVO_API_KEY", "")
    GMAIL_WEBHOOK_URL: Optional[str] = os.getenv("GMAIL_WEBHOOK_URL", "")
    GMAIL_SECRET_TOKEN: Optional[str] = os.getenv("GMAIL_SECRET_TOKEN", "")
    EMAIL_FROM: Optional[str] = os.getenv("EMAIL_FROM", os.getenv("MAIL_FROM", os.getenv("SMTP_FROM", "dedasema734012@gmail.com")))
    ADMIN_NOTIFICATION_EMAIL: Optional[str] = os.getenv("ADMIN_NOTIFICATION_EMAIL", "")
    COMERCIAL_EMAIL: str = os.getenv("COMERCIAL_EMAIL", os.getenv("ADMIN_NOTIFICATION_EMAIL", "dedasema734012@gmail.com"))
    REDIS_URL: Optional[str] = "redis://localhost:6379/0"
    tctokenservice: Optional[str] = os.getenv("tctokenservice", os.getenv("tcTokenService", os.getenv("TCTOKENSERVICE", "")))
    tctokensecret: Optional[str] = os.getenv("tctokensecret", os.getenv("tcTokenSecret", os.getenv("TCTOKENSECRET", "")))
    PAGOFACIL_BASE_URL: str = os.getenv("PAGOFACIL_BASE_URL", "https://masterqr.pagofacil.com.bo/api/services/v2")
    PAGOFACIL_CALLBACK_URL: Optional[str] = os.getenv("PAGOFACIL_CALLBACK_URL", "")
    AWS_ACCESS_KEY_ID: Optional[str] = os.getenv("AWS_ACCESS_KEY_ID", "")
    AWS_SECRET_ACCESS_KEY: Optional[str] = os.getenv("AWS_SECRET_ACCESS_KEY", "")
    AWS_REGION: str = os.getenv("AWS_REGION", "us-east-1")
    AWS_S3_BUCKET_NAME: Optional[str] = os.getenv("AWS_S3_BUCKET_NAME", "")
    AWS_S3_CUSTOM_DOMAIN: Optional[str] = os.getenv("AWS_S3_CUSTOM_DOMAIN", "")
    CORS_ORIGINS: Optional[str] = os.getenv("CORS_ORIGINS", "")

    @property
    def pagofacil_token_service(self) -> str:
        return (self.tctokenservice or os.getenv("tctokenservice") or os.getenv("tcTokenService") or os.getenv("TCTOKENSERVICE") or "").strip()

    @property
    def pagofacil_token_secret(self) -> str:
        return (self.tctokensecret or os.getenv("tctokensecret") or os.getenv("tcTokenSecret") or os.getenv("TCTOKENSECRET") or "").strip()

    @property
    def clean_frontend_url(self) -> str:
        url = str(self.FRONTEND_URL or "http://localhost:3000").strip()
        return url.rstrip("/")

    @property
    def sync_database_url(self) -> str:
        url = str(self.DATABASE_URL or "")
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql://", 1)
        return url

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()
