"""
Unit tests for CharacterGeneratorService
"""

from unittest.mock import AsyncMock

import pytest

from src.core.exceptions import AIServiceException
from src.models.internal import AIResponse, LLMGenerateParams
from src.services.character_generator import CharacterGeneratorService


@pytest.fixture
def mock_gemini_client():
    return AsyncMock()


@pytest.fixture
def mock_replicate_client():
    return AsyncMock()


@pytest.fixture
def character_service(mock_gemini_client, mock_replicate_client):
    return CharacterGeneratorService(gemini_client=mock_gemini_client, replicate_client=mock_replicate_client)


@pytest.mark.asyncio
async def test_generate_system_instructions_success(character_service, mock_gemini_client):
    """Test successful system instruction generation"""
    # Setup mock
    mock_gemini_client.generate_response.return_value = AIResponse(text="You are a pirate...", token_count=100)

    # Execute
    result = await character_service.generate_system_instructions("a pirate")

    # Assert
    assert result.system_instructions == "You are a pirate..."
    mock_gemini_client.generate_response.assert_called_once()
    params = mock_gemini_client.generate_response.call_args.args[0]
    assert isinstance(params, LLMGenerateParams)
    assert "a pirate" in params.user_message
    assert params.max_tokens == 2048


@pytest.mark.asyncio
async def test_validate_metadata_success_valid(character_service, mock_gemini_client, mock_replicate_client):
    """Test successful validation and metadata generation for valid character"""
    # Setup mock responses
    mock_response_json = """
    {
        "is_valid": true,
        "name": "pirate_bob",
        "display_name": "Pirate Bob",
        "image_prompt": "A cool pirate"
    }
    """
    mock_gemini_client.generate_response.return_value = AIResponse(text=mock_response_json, token_count=150)
    mock_replicate_client.generate_image.return_value = "https://example.com/avatar.jpg"

    # Execute
    result = await character_service.validate_and_generate_metadata("Original detailed instructions...")

    # Assert
    assert result.is_valid is True
    assert result.name == "pirate_bob"
    assert result.avatar_url == "https://example.com/avatar.jpg"
    mock_replicate_client.generate_image.assert_called_once()


@pytest.mark.asyncio
async def test_validate_metadata_invalid_nsfw(character_service, mock_gemini_client, mock_replicate_client):
    """Test validation failing for NSFW content"""
    # Setup mock responses
    mock_response_json = """
    {
        "is_valid": false,
        "reason": "NSFW content detected"
    }
    """
    mock_gemini_client.generate_response.return_value = AIResponse(text=mock_response_json, token_count=50)

    # Execute
    result = await character_service.validate_and_generate_metadata("Some sketchy instructions...")

    # Assert
    assert result.is_valid is False
    assert result.reason == "NSFW content detected"
    mock_replicate_client.generate_image.assert_not_called()


@pytest.mark.asyncio
async def test_validate_metadata_gemini_error(character_service, mock_gemini_client):
    """Test error handling when Gemini fails"""
    # Setup mock to raise exception
    mock_gemini_client.generate_response.side_effect = Exception("API Error")

    # Execute & Assert
    with pytest.raises(AIServiceException) as exc:
        await character_service.validate_and_generate_metadata("test")

    assert "Failed to process character metadata" in str(exc.value)
