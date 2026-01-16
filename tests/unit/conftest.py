"""
Fixtures for unit tests
"""

from datetime import UTC, datetime

import pytest

from src.models.entities import AIInfluencer, Conversation, InfluencerStatus, Message, MessageRole, MessageType
from src.models.internal import AIProviderHealth


@pytest.fixture
def sample_influencer():
    """Create a sample AIInfluencer entity"""
    return AIInfluencer(
        id="infl-123",
        name="test_ai",
        display_name="Test AI",
        system_instructions="You are a helpful assistant.",
        initial_greeting="Hello! How can I help?",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        is_active=InfluencerStatus.ACTIVE,
        is_nsfw=False,
    )


@pytest.fixture
def sample_conversation():
    """Create a sample Conversation entity"""
    return Conversation(
        id="conv-123",
        user_id="user-456",
        influencer_id="infl-123",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        metadata={"memories": {}},
    )


@pytest.fixture
def sample_message():
    """Create a sample Message entity"""
    return Message(
        id="msg-789",
        conversation_id="conv-123",
        role=MessageRole.USER,
        content="Hello world",
        message_type=MessageType.TEXT,
        created_at=datetime.now(UTC),
    )


@pytest.fixture
def sample_health_result():
    """Create a sample AIProviderHealth result"""
    return AIProviderHealth(status="up", latency_ms=150.0)
