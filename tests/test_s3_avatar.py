import io
import uuid
from unittest.mock import patch, MagicMock
import pytest
from botocore.exceptions import ClientError
from fastapi import UploadFile

from app.models.administrador import Administrador
from app.models.suscriptor import Suscriptor
from app.services.s3_service import is_s3_configured, upload_file_to_s3


def test_is_s3_configured():
    with patch("app.services.s3_service.settings") as mock_settings:
        mock_settings.AWS_S3_BUCKET_NAME = ""
        mock_settings.AWS_ACCESS_KEY_ID = ""
        mock_settings.AWS_SECRET_ACCESS_KEY = ""
        assert is_s3_configured() is False

        mock_settings.AWS_S3_BUCKET_NAME = "my-test-bucket"
        mock_settings.AWS_ACCESS_KEY_ID = "AKIA123456789"
        mock_settings.AWS_SECRET_ACCESS_KEY = "SECRET123456789"
        assert is_s3_configured() is True


@pytest.mark.asyncio
async def test_upload_file_to_s3_success():
    with patch("app.services.s3_service.settings") as mock_settings, \
         patch("app.services.s3_service.get_s3_client") as mock_get_client:
        mock_settings.AWS_S3_BUCKET_NAME = "surveys-bucket"
        mock_settings.AWS_REGION = "us-east-1"
        mock_settings.AWS_ACCESS_KEY_ID = "AKIA123"
        mock_settings.AWS_SECRET_ACCESS_KEY = "SECRET123"
        mock_settings.AWS_S3_CUSTOM_DOMAIN = ""

        mock_s3 = MagicMock()
        mock_get_client.return_value = mock_s3

        file_content = b"fake-image-bytes"
        upload_file = UploadFile(filename="avatar.png", file=io.BytesIO(file_content))
        upload_file.headers = {"content-type": "image/png"}

        url = await upload_file_to_s3(upload_file, "avatars/user1_12345678.png")

        assert url == "https://surveys-bucket.s3.us-east-1.amazonaws.com/avatars/user1_12345678.png"
        mock_s3.upload_fileobj.assert_called_once()


@pytest.mark.asyncio
async def test_upload_file_to_s3_with_custom_domain():
    with patch("app.services.s3_service.settings") as mock_settings, \
         patch("app.services.s3_service.get_s3_client") as mock_get_client:
        mock_settings.AWS_S3_BUCKET_NAME = "surveys-bucket"
        mock_settings.AWS_REGION = "us-east-1"
        mock_settings.AWS_ACCESS_KEY_ID = "AKIA123"
        mock_settings.AWS_SECRET_ACCESS_KEY = "SECRET123"
        mock_settings.AWS_S3_CUSTOM_DOMAIN = "cdn.surveysaas.com"

        mock_s3 = MagicMock()
        mock_get_client.return_value = mock_s3

        upload_file = UploadFile(filename="avatar.jpg", file=io.BytesIO(b"img"))
        upload_file.headers = {"content-type": "image/jpeg"}

        url = await upload_file_to_s3(upload_file, "avatars/user2_abcd.jpg")
        assert url == "https://cdn.surveysaas.com/avatars/user2_abcd.jpg"


def test_auth_perfil_foto_rejects_non_image(client, empresa_headers):
    files = {"file": ("document.pdf", b"%PDF-1.4 dummy", "application/pdf")}
    res = client.post("/auth/perfil/foto", files=files, headers=empresa_headers)
    assert res.status_code == 400
    assert "imagen" in res.json()["detail"].lower()


def test_auth_perfil_foto_s3_upload(client, db_session, empresa_headers):
    # Ensure test subscriber exists in DB
    empresa_id = uuid.UUID("00000000-0000-0000-0000-000000000002")
    empresa = db_session.get(Suscriptor, empresa_id)
    if not empresa:
        empresa = Suscriptor(
            id=empresa_id,
            nombre="Empresa S3 Test",
            email="empresa_s3@test.com",
            password_hash="dummyhash",
            rol_id=1,
            estado="activo"
        )
        db_session.add(empresa)
        db_session.commit()

    with patch("app.routers.auth.is_s3_configured", return_value=True), \
         patch("app.routers.auth.upload_file_to_s3") as mock_upload:
        expected_url = "https://test-bucket.s3.us-east-1.amazonaws.com/avatars/empresa_test.png"
        mock_upload.return_value = expected_url

        files = {"file": ("avatar.png", b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR", "image/png")}
        res = client.post("/auth/perfil/foto", files=files, headers=empresa_headers)

        assert res.status_code == 200
        data = res.json()
        assert data["foto_url"] == expected_url
        assert data["mensaje"] == "Foto de perfil actualizada exitosamente"

        # Verify DB updated
        db_session.refresh(empresa)
        assert empresa.foto_url == expected_url
