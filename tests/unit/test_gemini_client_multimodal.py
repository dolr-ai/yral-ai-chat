from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.models.entities import Message, MessageRole, MessageType
from src.services.gemini_client import GeminiClient


class TestGeminiMultimodal:
    @pytest.fixture
    def client(self):
        with patch("src.services.gemini_client.settings") as mock_settings:
            mock_settings.gemini_api_key = "test-key"
            mock_settings.gemini_model = "gemini-pro"
            with (
                patch("httpx.AsyncClient"),
                patch("src.services.gemini_client.genai.Client"),
            ):
                return GeminiClient()

    @pytest.mark.asyncio
    async def test_build_contents_with_http_urls(self, client):
        """Test that build_contents uses file_uri for HTTP media URLs"""
        user_message = "What is in this image?"
        media_urls = ["https://example.com/image.jpg"]
        
        contents = await client._build_contents(user_message, None, media_urls)
        
        # Verify structure
        assert len(contents) == 1
        assert contents[0].role == "user"
        parts = contents[0].parts
        
        # Should have text and file_data
        assert len(parts) == 2
        assert parts[0].text == user_message
        assert parts[1].file_data.file_uri == "https://example.com/image.jpg"
        assert parts[1].file_data.mime_type == "image/jpeg"

    @pytest.mark.asyncio
    async def test_build_contents_with_history(self, client):
        """Test that build_contents handles history with multimodal messages"""
        history = [
            Message(
                id="1",
                conversation_id="conv1",
                role=MessageRole.USER,
                content="Check this out",
                message_type=MessageType.IMAGE,
                media_urls=["https://example.com/old.png"],
                created_at=MagicMock()
            )
        ]
        user_message = "And this one?"
        media_urls = ["https://example.com/new.jpg"]
        
        contents = await client._build_contents(user_message, history, media_urls)
        
        assert len(contents) == 2
        
        # Old message
        assert contents[0].role == "user"
        assert contents[0].parts[1].file_data.file_uri == "https://example.com/old.png"
        assert contents[0].parts[1].file_data.mime_type == "image/png"
        
        # New message
        assert contents[1].role == "user"
        assert contents[1].parts[1].file_data.file_uri == "https://example.com/new.jpg"

    @pytest.mark.asyncio
    async def test_transcribe_audio_with_link(self, client):
        """Test that transcribe_audio uses direct link and retry wrapper"""
        audio_url = "https://example.com/audio.mp3"
        transcription_text = "Hello world"

        # Mock the internal retry call
        with patch.object(client, "_transcribe_audio_with_link", new_callable=AsyncMock) as mock_transcribe:
            mock_response = MagicMock()
            mock_response.text = transcription_text
            mock_transcribe.return_value = mock_response

            result = await client.transcribe_audio(audio_url)

            assert result == transcription_text
            mock_transcribe.assert_called_once_with(
                audio_url, "Please transcribe this audio file accurately. Only return the transcription text without any additional commentary."
            )
