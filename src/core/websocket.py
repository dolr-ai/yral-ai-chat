"""
WebSocket connection manager for real-time inbox updates
"""

from typing import Any
from uuid import UUID

from fastapi import WebSocket
from loguru import logger


class ConnectionManager:
    """Manages WebSocket connections for real-time inbox updates"""

    def __init__(self):
        # Map of user_id -> list of WebSocket connections
        self.active_connections: dict[str, list[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, user_id: str):
        """Accept and register a new WebSocket connection"""
        await websocket.accept()
        
        if user_id not in self.active_connections:
            self.active_connections[user_id] = []
        
        self.active_connections[user_id].append(websocket)
        logger.info(f"WebSocket connected for user {user_id}. Total connections: {len(self.active_connections[user_id])}")

    def disconnect(self, websocket: WebSocket, user_id: str):
        """Remove a WebSocket connection"""
        if user_id in self.active_connections:
            try:
                self.active_connections[user_id].remove(websocket)
                logger.info(f"WebSocket disconnected for user {user_id}. Remaining connections: {len(self.active_connections[user_id])}")
                
                # Clean up empty lists
                if not self.active_connections[user_id]:
                    del self.active_connections[user_id]
            except ValueError:
                logger.warning(f"Attempted to disconnect non-existent WebSocket for user {user_id}")

    async def send_personal_message(self, message: dict[str, Any], user_id: str):
        """Send a message to all connections of a specific user"""
        if user_id not in self.active_connections:
            logger.debug(f"No active connections for user {user_id}")
            return

        disconnected = []
        for connection in self.active_connections[user_id]:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.warning(f"Failed to send message to user {user_id}: {e}")
                disconnected.append(connection)

        # Clean up failed connections
        for conn in disconnected:
            self.disconnect(conn, user_id)

    async def broadcast_new_message(
        self,
        user_id: str,
        conversation_id: UUID,
        message: dict[str, Any],
        influencer: dict[str, Any],
        unread_count: int,
    ):
        """Broadcast a new message event to a user"""
        event = {
            "event": "new_message",
            "data": {
                "conversation_id": str(conversation_id),
                "message": message,
                "influencer_id": influencer.get("id"),
                "influencer": influencer,
                "unread_count": unread_count,
            },
        }
        await self.send_personal_message(event, user_id)

    async def broadcast_conversation_read(
        self,
        user_id: str,
        conversation_id: UUID,
        read_at: str,
    ):
        """Broadcast a conversation read event to a user"""
        event = {
            "event": "conversation_read",
            "data": {
                "conversation_id": str(conversation_id),
                "unread_count": 0,
                "read_at": read_at,
            },
        }
        await self.send_personal_message(event, user_id)

    async def broadcast_typing_status(
        self,
        user_id: str,
        conversation_id: UUID,
        influencer_id: str,
        is_typing: bool,
    ):
        """Broadcast typing indicator to a user"""
        event = {
            "event": "typing_status",
            "data": {
                "conversation_id": str(conversation_id),
                "influencer_id": influencer_id,
                "is_typing": is_typing,
            },
        }
        await self.send_personal_message(event, user_id)


# Global connection manager instance
manager = ConnectionManager()
