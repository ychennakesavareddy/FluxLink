from fastapi import WebSocket
from typing import Dict, Set, Optional, List
import json
import logging

logger = logging.getLogger("chennalink.ws")

class ConnectionManager:
    def __init__(self):
        # session_id -> {device_key -> WebSocket}
        self.active_connections: Dict[str, Dict[str, WebSocket]] = {}

    def get_active_count(self, session_id: str) -> int:
        conns = self.active_connections.get(session_id, {})
        return len(set(conns.values()))

    async def connect(self, websocket: WebSocket, session_id: str, device_keys: List[str]):
        if session_id not in self.active_connections:
            self.active_connections[session_id] = {}
        
        session_conns = self.active_connections[session_id]
        
        # If any of the keys already has an active connection, close the old one
        for key in device_keys:
            if key in session_conns:
                old_ws = session_conns[key]
                if old_ws != websocket:
                    try:
                        await old_ws.close(code=1000, reason="Replaced by new connection")
                    except Exception:
                        pass
        
        # Map all provided device identifiers to this websocket
        for key in device_keys:
            session_conns[key] = websocket

    def disconnect(self, session_id: str, websocket: WebSocket):
        if session_id in self.active_connections:
            session_conns = self.active_connections[session_id]
            to_remove = [k for k, v in session_conns.items() if v == websocket]
            for k in to_remove:
                del session_conns[k]
            if not session_conns:
                del self.active_connections[session_id]

    def get_socket(self, session_id: str, device_keys: List[str]) -> Optional[WebSocket]:
        session_conns = self.active_connections.get(session_id, {})
        for key in device_keys:
            if key in session_conns:
                return session_conns[key]
        return None

    async def send_personal_message(self, message: str, session_id: str, device_key: str):
        ws = self.get_socket(session_id, [device_key])
        if ws:
            await ws.send_text(message)

    async def broadcast_to_session(self, message: str, session_id: str, exclude_websocket: WebSocket = None):
        if session_id in self.active_connections:
            unique_sockets = set(self.active_connections[session_id].values())
            for ws in unique_sockets:
                if ws != exclude_websocket:
                    try:
                        await ws.send_text(message)
                    except Exception as e:
                        logger.warning(f"Failed to send broadcast to socket: {e}")

manager = ConnectionManager()
