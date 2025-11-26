"""
Domain entity models
"""
from enum import Enum
from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field
from uuid import UUID


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
    id: UUID
    name: str
    display_name: str
    avatar_url: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    system_instructions: str
    personality_traits: Dict[str, Any] = Field(default_factory=dict)
    initial_greeting: Optional[str] = None
    is_active: bool = True
    created_at: datetime
    updated_at: datetime
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    # Optional field for conversation count
    conversation_count: Optional[int] = None

    class Config:
        from_attributes = True


class Conversation(BaseModel):
    """Conversation entity"""
    id: UUID
    user_id: str
    influencer_id: UUID
    created_at: datetime
    updated_at: datetime
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    # Optional nested fields
    influencer: Optional[AIInfluencer] = None
    message_count: Optional[int] = None
    last_message: Optional[Dict[str, Any]] = None

    class Config:
        from_attributes = True


class Message(BaseModel):
    """Message entity"""
    id: UUID
    conversation_id: UUID
    role: MessageRole
    content: Optional[str] = None
    message_type: MessageType
    media_urls: List[str] = Field(default_factory=list)
    audio_url: Optional[str] = None
    audio_duration_seconds: Optional[int] = None
    token_count: Optional[int] = None
    created_at: datetime
    metadata: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        from_attributes = True


