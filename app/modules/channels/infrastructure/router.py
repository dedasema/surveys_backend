"""
Channels Router Adapter (WhatsApp & Vapi Voice).
"""

from app.routers.whatsapp_router import router as whatsapp_router
from app.routers.vapi_router import router as vapi_router

__all__ = ["whatsapp_router", "vapi_router"]
