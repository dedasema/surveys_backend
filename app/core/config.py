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
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    WHAPI_TOKEN: Optional[str] = ""
    WHAPI_API_URL: str = "https://gate.whapi.cloud"
    OPENAI_API_KEY: Optional[str] = ""
    VAPI_API_URL: Optional[str] = "https://api.vapi.ai"
    VAPI_API_KEY: Optional[str] = ""
    API_BASE_URL: Optional[str] = "http://localhost:8000"
    VAPI_PHONE_NUMBER_ID: Optional[str] = ""
    VAPI_ASSISTANT_ID: Optional[str] = ""
    STRIPE_SECRET_KEY: Optional[str] = ""
    STRIPE_PUBLIC_KEY: Optional[str] = ""
    STRIPE_WEBHOOK_SECRET: Optional[str] = ""
    FRONTEND_URL: str = os.getenv("FRONTEND_URL", "http://localhost:3000")
    SURVEY_LINK_EXPIRY_DAYS: int = 7
    SMTP_SERVER: Optional[str] = "localhost"
    SMTP_PORT: int = 587
    SMTP_USERNAME: Optional[str] = ""
    SMTP_PASSWORD: Optional[str] = ""
    RESEND_API_KEY: Optional[str] = ""
    EMAIL_FROM: Optional[str] = "SurveySaaS <onboarding@resend.dev>"
    REDIS_URL: Optional[str] = "redis://localhost:6379/0"

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
