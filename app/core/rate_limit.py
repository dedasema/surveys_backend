# app/core/rate_limit.py
import time
import logging
from collections import defaultdict
from fastapi import Request, HTTPException, status

logger = logging.getLogger(__name__)

# Almacén en memoria: IP -> lista de timestamps
_request_history = defaultdict(list)


def rate_limit_ip(max_requests: int = 5, window_seconds: int = 60):
    """
    Dependencia FastAPI que aplica rate limiting basado en la dirección IP del cliente.
    Si se excede el límite permitido dentro de la ventana, retorna 429 Too Many Requests.
    """
    def dependency(request: Request):
        # Determinar IP considerando encabezados proxy
        forwarded_for = request.headers.get("x-forwarded-for")
        if forwarded_for:
            client_ip = forwarded_for.split(",")[0].strip()
        else:
            client_ip = request.client.host if request.client else "127.0.0.1"

        now = time.time()
        cutoff = now - window_seconds

        # Limpiar llamadas fuera de la ventana
        history = [ts for ts in _request_history[client_ip] if ts > cutoff]
        _request_history[client_ip] = history

        if len(history) >= max_requests:
            logger.warning("Rate limit excedido para IP %s: %d peticiones en %ds", client_ip, len(history), window_seconds)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Demasiadas solicitudes. Límite permitido: {max_requests} por minuto.",
            )

        _request_history[client_ip].append(now)
        return client_ip

    return dependency
