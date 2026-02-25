"""
WebSocket connection manager for real-time inbox updates
"""

from typing import Any

from fastapi import WebSocket
from loguru import logger
from pydantic import BaseModel

from src.models.responses import InfluencerBasicInfo, MessageResponse
from src.models.websocket_events import (
    ConversationReadEvent,
    ConversationReadEventData,
    NewMessageEvent,
    NewMessageEventData,
    TypingStatusEvent,
    TypingStatusEventData,
)


class ConnectionManager:
    """Manages WebSocket connections for real-time inbox updates"""

    def __init__(self) -> None:
        # Map of user_id -> list of WebSocket connections
        self.active_connections: dict[str, list[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, user_id: str):
        """Accept and register a new WebSocket connection"""
        await websocket.accept()

        if user_id not in self.active_connections:
            self.active_connections[user_id] = []

        self.active_connections[user_id].append(websocket)
        logger.info(
            f"WebSocket connected for user {user_id}. Total connections: {len(self.active_connections[user_id])}"
        )

    def disconnect(self, websocket: WebSocket, user_id: str):
        """Remove a WebSocket connection"""
        if user_id in self.active_connections:
            try:
                self.active_connections[user_id].remove(websocket)
                logger.info(
                    f"WebSocket disconnected for user {user_id}. Remaining connections: {len(self.active_connections[user_id])}"
                )

                # Clean up empty lists
                if not self.active_connections[user_id]:
                    del self.active_connections[user_id]
            except ValueError:
                logger.warning(f"Attempted to disconnect non-existent WebSocket for user {user_id}")

    async def emit_to_user(self, message: dict[str, Any] | BaseModel, user_id: str):
        """Send a message/event to all active connections for a specific user"""
        if user_id not in self.active_connections:
            return

        payload = message.model_dump(mode="json") if isinstance(message, BaseModel) else message

        connections = self.active_connections[user_id]
        logger.debug(f"Emitting message to user {user_id} across {len(connections)} connections")

        # Collect dead connections to remove later
        dead_connections = []
        for connection in connections:
            try:
                await connection.send_json(payload)
            except Exception as e:
                logger.warning(f"Failed to send websocket message: {e}")
                dead_connections.append(connection)

        # Cleanup dead connections
        for dead in dead_connections:
            if dead in connections:
                connections.remove(dead)

    async def emit_new_message_event(
        self,
        user_id: str,
        conversation_id: str,
        message: MessageResponse,
        influencer: InfluencerBasicInfo,
        unread_count: int,
    ):
        """Emit a new message event to a user"""
        event = NewMessageEvent(
            data=NewMessageEventData(
                conversation_id=conversation_id,
                message=message,
                influencer_id=influencer.id,
                influencer=influencer,
                unread_count=unread_count,
            )
        )
        await self.emit_to_user(event, user_id)

    async def emit_conversation_read_event(
        self,
        user_id: str,
        conversation_id: str,
        read_at: str,
    ):
        """Emit a conversation read event to a user"""
        event = ConversationReadEvent(
            data=ConversationReadEventData(
                conversation_id=conversation_id,
                unread_count=0,
                read_at=read_at,
            )
        )
        await self.emit_to_user(event, user_id)

    async def emit_typing_status_event(
        self,
        user_id: str,
        conversation_id: str,
        influencer_id: str,
        is_typing: bool,
    ):
        """Emit typing indicator to a user"""
        event = TypingStatusEvent(
            data=TypingStatusEventData(
                conversation_id=conversation_id,
                influencer_id=influencer_id,
                is_typing=is_typing,
            )
        )
        await self.emit_to_user(event, user_id)


# Global connection manager instance
manager = ConnectionManager()
