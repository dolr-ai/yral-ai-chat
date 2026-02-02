"""
Pydantic models for WebSocket events
Used for both runtime validation (optional) and documentation (OpenAPI)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from src.models.responses import InfluencerBasicInfo, MessageResponse

class NewMessageEventData(BaseModel):
    """Data payload for the new_message event"""
    conversation_id: str = Field(..., description="ID of the conversation")
    message: MessageResponse = Field(..., description="The newly created message")
    influencer_id: str = Field(..., description="ID of the influencer")
    influencer: InfluencerBasicInfo = Field(..., description="Influencer basic details")
    unread_count: int = Field(..., description="Current unread count for the user in this conversation")

class NewMessageEvent(BaseModel):
    """Event sent when a new message is created"""
    event: Literal["new_message"] = "new_message"
    data: NewMessageEventData

class ConversationReadEventData(BaseModel):
    """Data payload for the conversation_read event"""
    conversation_id: str = Field(..., description="ID of the conversation")
    unread_count: int = Field(0, description="New unread count (always 0)")
    read_at: str = Field(..., description="ISO timestamp of when it was marked as read")

class ConversationReadEvent(BaseModel):
    """Event sent when a conversation is marked as read"""
    event: Literal["conversation_read"] = "conversation_read"
    data: ConversationReadEventData

class TypingStatusEventData(BaseModel):
    """Data payload for the typing_status event"""
    conversation_id: str = Field(..., description="ID of the conversation")
    influencer_id: str = Field(..., description="ID of the influencer")
    is_typing: bool = Field(..., description="Whether the influencer is currently typing")

class TypingStatusEvent(BaseModel):
    """Event sent when an influencer starts/stops typing"""
    event: Literal["typing_status"] = "typing_status"
    data: TypingStatusEventData

# Union of all possible WebSocket events for documentation
WebSocketEvent = NewMessageEvent | ConversationReadEvent | TypingStatusEvent
