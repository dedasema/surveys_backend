"""
Catalogos and Anuncios Router Adapter.
"""

from app.routers.catalogos import router as catalogos_router
from app.routers.anuncios_router import admin_router as anuncios_admin_router, public_router as anuncios_public_router

__all__ = ["catalogos_router", "anuncios_admin_router", "anuncios_public_router"]
