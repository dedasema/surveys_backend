# app/services/websocket_manager.py
import json
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone
from fastapi import WebSocket

logger = logging.getLogger(__name__)

class ConnectionManager:
    """
    Gestor centralizado de conexiones WebSocket para sincronización en tiempo real (RF24).
    Permite salas por campaña y canal general de notificaciones de plataforma.
    """
    def __init__(self):
        # Mapeo de campana_id (str) -> lista de WebSockets
        self.campaign_rooms: Dict[str, List[WebSocket]] = {}
        # Conexiones generales (sin filtro de campaña específica)
        self.general_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket, campana_id: Optional[str] = None):
        await websocket.accept()
        if campana_id:
            c_key = str(campana_id)
            if c_key not in self.campaign_rooms:
                self.campaign_rooms[c_key] = []
            self.campaign_rooms[c_key].append(websocket)
            logger.info("WebSocket conectado a sala de campaña %s", c_key)
        else:
            self.general_connections.append(websocket)
            logger.info("WebSocket conectado a canal general")

    def disconnect(self, websocket: WebSocket, campana_id: Optional[str] = None):
        if campana_id:
            c_key = str(campana_id)
            if c_key in self.campaign_rooms and websocket in self.campaign_rooms[c_key]:
                self.campaign_rooms[c_key].remove(websocket)
                if not self.campaign_rooms[c_key]:
                    del self.campaign_rooms[c_key]
                logger.info("WebSocket desconectado de sala %s", c_key)
        else:
            if websocket in self.general_connections:
                self.general_connections.remove(websocket)
                logger.info("WebSocket desconectado de canal general")

    async def send_personal_message(self, message: Dict[str, Any], websocket: WebSocket):
        try:
            await websocket.send_text(json.dumps(message, default=str))
        except Exception as e:
            logger.warning("Error enviando mensaje WebSocket personal: %s", e)

    async def broadcast(
        self,
        event_type: str,
        payload: Any,
        campana_id: Optional[str] = None
    ):
        """
        Emite un mensaje tipado a los suscriptores de la campaña y al canal general.
        Tipos estándar: 'nueva_respuesta', 'actualizacion_metricas', 'alerta_fraude', 'decision_agente'.
        """
        message = {
            "type": event_type,
            "payload": payload,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        msg_str = json.dumps(message, default=str)

        destinatarios: List[WebSocket] = list(self.general_connections)
        if campana_id:
            c_key = str(campana_id)
            if c_key in self.campaign_rooms:
                destinatarios.extend(self.campaign_rooms[c_key])

        desconectados = []
        for ws in set(destinatarios):
            try:
                await ws.send_text(msg_str)
            except Exception as e:
                logger.warning("Fallo al emitir por WebSocket: %s", e)
                desconectados.append(ws)

        # Limpieza de conexiones muertas
        for dead_ws in desconectados:
            self.disconnect(dead_ws, campana_id)
            if dead_ws in self.general_connections:
                self.general_connections.remove(dead_ws)

# Instancia global única
ws_manager = ConnectionManager()
