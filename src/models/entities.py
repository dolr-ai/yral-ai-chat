"""
Domain entity models
"""
from datetime import datetime
from enum import Enum
from typing import Any

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
    personality_traits: dict[str, Any] = Field(default_factory=dict)
    initial_greeting: str | None = None
    suggested_messages: list[str] = Field(default_factory=list)
    is_active: bool = True
    created_at: datetime
    updated_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)

    # Optional field for conversation count
    conversation_count: int | None = None


class Conversation(BaseModel):
    """Conversation entity"""
    model_config = ConfigDict(from_attributes=True)
    
    id: str  # Changed from UUID to str
    user_id: str
    influencer_id: str  # Changed from UUID to str to support IC Principal IDs
    created_at: datetime
    updated_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)

    # Optional nested fields
    influencer: AIInfluencer | None = None
    message_count: int | None = None
    last_message: dict[str, Any] | None = None


class Message(BaseModel):
    """Message entity"""
    model_config = ConfigDict(from_attributes=True)
    
    id: str  # Changed from UUID to str
    conversation_id: str  # Changed from UUID to str
    role: MessageRole
    content: str | None = None
    message_type: MessageType
    media_urls: list[str] = Field(default_factory=list)
    audio_url: str | None = None
    audio_duration_seconds: int | None = None
    token_count: int | None = None
    created_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)


