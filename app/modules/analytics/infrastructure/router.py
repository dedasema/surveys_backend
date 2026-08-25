"""
Analytics, NLP, PDF Export, and Dashboard Routers (Adapters).
"""

from app.routers.analytics_router import router as analytics_router
from app.routers.nlp_router import router as nlp_router
from app.routers.pdf_router import router as pdf_router
from app.routers.dashboard_router import router as dashboard_router

__all__ = ["analytics_router", "nlp_router", "pdf_router", "dashboard_router"]
