# app/routers/websocket_router.py
import json
import logging
from typing import Optional
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.websocket_manager import ws_manager

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Sincronización en Vivo / WebSockets (RF24)"])

@router.websocket("/ws/campanas/{campana_id}")
async def websocket_campana_endpoint(websocket: WebSocket, campana_id: str):
    await ws_manager.connect(websocket, campana_id=campana_id)
    try:
        # Enviar confirmación de conexión
        await ws_manager.send_personal_message(
            {
                "type": "conexion_establecida",
                "payload": {"campana_id": campana_id, "mensaje": "Suscripción activa a eventos en vivo"}
            },
            websocket
        )

        while True:
            raw_data = await websocket.receive_text()
            try:
                msg = json.loads(raw_data)
                action = msg.get("action")
                if action == "ping":
                    await ws_manager.send_personal_message({"type": "pong", "payload": {}}, websocket)
                elif action == "subscribe":
                    # Ya conectado
                    pass
            except Exception as e:
                logger.debug("Error procesando mensaje entrante WebSocket: %s", e)
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket, campana_id=campana_id)
    except Exception as e:
        logger.error("Error inesperado en WebSocket de campaña: %s", e)
        ws_manager.disconnect(websocket, campana_id=campana_id)

@router.websocket("/ws/general")
async def websocket_general_endpoint(websocket: WebSocket):
    await ws_manager.connect(websocket, campana_id=None)
    try:
        await ws_manager.send_personal_message(
            {
                "type": "conexion_establecida",
                "payload": {"mensaje": "Conexión general a eventos de plataforma establecida"}
            },
            websocket
        )

        while True:
            raw_data = await websocket.receive_text()
            try:
                msg = json.loads(raw_data)
                if msg.get("action") == "ping":
                    await ws_manager.send_personal_message({"type": "pong", "payload": {}}, websocket)
            except Exception:
                pass
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket, campana_id=None)
    except Exception as e:
        logger.error("Error inesperado en WebSocket general: %s", e)
        ws_manager.disconnect(websocket, campana_id=None)
