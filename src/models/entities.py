"""
Domain entity models
"""

from __future__ import annotations

from datetime import datetime  # noqa: TC003
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class MessageType(str, Enum):
    """Message type enumeration"""

    TEXT = "text"
    MULTIMODAL = "multimodal"
    IMAGE = "image"
    AUDIO = "audio"


class MessageRole(str, Enum):
    """Message role enumeration"""

    USER = "user"
    ASSISTANT = "assistant"


class LastMessageInfo(BaseModel):
    """Last message information for conversation list"""

    model_config = ConfigDict(from_attributes=True, use_enum_values=True)

    content: str | None = None
    role: MessageRole
    created_at: datetime


class InfluencerStatus(str, Enum):
    """Influencer status enumeration"""

    ACTIVE = "active"
    COMING_SOON = "coming_soon"
    DISCONTINUED = "discontinued"


class AIInfluencer(BaseModel):
    """AI Influencer entity"""

    model_config = ConfigDict(from_attributes=True)

    id: str  # Changed from UUID to str to support IC Principal IDs
    name: str
    display_name: str
    avatar_url: str | None = None
    description: str | None = None
    category: str | None = None
    system_instructions: str
    personality_traits: dict[str, object] = Field(default_factory=dict)
    initial_greeting: str | None = None
    suggested_messages: list[str] = Field(default_factory=list)
    is_active: InfluencerStatus = InfluencerStatus.ACTIVE
    is_nsfw: bool = Field(default=False, description="Whether this influencer handles NSFW content")
    parent_principal_id: str | None = None
    source: str | None = None
    created_at: datetime
    updated_at: datetime
    metadata: dict[str, object] = Field(default_factory=dict)

    conversation_count: int | None = None


class Conversation(BaseModel):
    """Conversation entity"""

    model_config = ConfigDict(from_attributes=True)

    id: str  # Changed from UUID to str
    user_id: str
    influencer_id: str  # Changed from UUID to str to support IC Principal IDs
    created_at: datetime
    updated_at: datetime
    metadata: dict[str, object] = Field(default_factory=dict)

    influencer: AIInfluencer | None = None
    message_count: int | None = None
    last_message: LastMessageInfo | None = None
    recent_messages: list[Message] | None = None


class Message(BaseModel):
    """Message entity"""

    model_config = ConfigDict(from_attributes=True)

    id: str  # Changed from UUID to str
    conversation_id: str  # Changed from UUID to str
    role: MessageRole
    content: str | None = None
    message_type: MessageType
    media_urls: list[str] = Field(default_factory=list, description="List of storage keys for image files")
    audio_url: str | None = Field(None, description="Storage key for audio file")
    audio_duration_seconds: int | None = None
    token_count: int | None = None
    created_at: datetime
    metadata: dict[str, object] = Field(default_factory=dict)
