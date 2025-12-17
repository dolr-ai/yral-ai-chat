"""
Unit tests for Pydantic models
"""
import pytest
from pydantic import ValidationError

from src.models.entities import MessageType
from src.models.requests import CreateConversationRequest, SendMessageRequest
from src.models.responses import InfluencerBasicInfo


class TestCreateConversationRequest:
    """Tests for CreateConversationRequest model"""

    def test_valid_request(self):
        """Test creating valid conversation request accepts string IDs (UUID or IC principal)"""
        value = "550e8400-e29b-41d4-a716-446655440000"
        request = CreateConversationRequest(influencer_id=value)
        assert isinstance(request.influencer_id, str)

    def test_allows_non_uuid_ids(self):
        """Test that non-UUID influencer IDs (e.g. IC Principals) are accepted as strings"""
        value = "not-a-uuid"
        request = CreateConversationRequest(influencer_id=value)
        assert request.influencer_id == value


class TestSendMessageRequest:
    """Tests for SendMessageRequest model"""

    def test_text_message(self):
        """Test creating text message request"""
        request = SendMessageRequest(
            message_type=MessageType.TEXT,
            content="Hello, AI!"
        )
        assert request.message_type == MessageType.TEXT
        assert request.content == "Hello, AI!"
        # media_urls can be None for TEXT messages (validator allows it)
        assert request.media_urls is None or request.media_urls == []

    def test_image_message(self):
        """Test creating image message request"""
        request = SendMessageRequest(
            message_type=MessageType.IMAGE,
            content="What's in this image?",
            media_urls=["https://example.com/image.jpg"]
        )
        assert request.message_type == MessageType.IMAGE
        assert len(request.media_urls) == 1

    def test_text_message_without_content_fails(self):
        """Test that text message without content fails validation"""
        with pytest.raises(ValidationError, match="content is required"):
            SendMessageRequest(
                message_type=MessageType.TEXT,
                content=""
            )

    def test_image_message_without_urls_fails(self):
        """Test that image message without URLs fails validation"""
        with pytest.raises(ValidationError, match="media_urls is required"):
            SendMessageRequest(
                message_type=MessageType.IMAGE,
                content="Check this",
                media_urls=[]
            )

    def test_audio_message(self):
        """Test creating audio message request"""
        request = SendMessageRequest(
            message_type=MessageType.AUDIO,
            audio_url="https://example.com/audio.mp3",
            audio_duration_seconds=45
        )
        assert request.message_type == MessageType.AUDIO
        assert request.audio_url is not None
        assert request.audio_duration_seconds == 45

    def test_content_max_length(self):
        """Test content length validation"""
        long_content = "a" * 5000
        with pytest.raises(ValidationError):
            SendMessageRequest(
                message_type=MessageType.TEXT,
                content=long_content
            )


class TestInfluencerBasicInfo:
    """Tests for InfluencerBasicInfo response model"""

    def test_valid_influencer(self):
        """Test creating valid influencer info"""
        info = InfluencerBasicInfo(
            id="550e8400-e29b-41d4-a716-446655440000",
            name="tech_guru",
            display_name="Tech Guru AI",
            avatar_url="https://example.com/avatar.jpg"
        )
        assert info.name == "tech_guru"
        assert info.display_name == "Tech Guru AI"

    def test_optional_avatar(self):
        """Test that avatar_url is optional"""
        info = InfluencerBasicInfo(
            id="550e8400-e29b-41d4-a716-446655440000",
            name="tech_guru",
            display_name="Tech Guru AI"
        )
        assert info.avatar_url is None
