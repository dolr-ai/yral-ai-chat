
from unittest.mock import AsyncMock

import pytest

from src.models.internal import AIResponse
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
async def test_validate_metadata_detects_refusal_in_raw_text(character_service, mock_gemini_client):
    """Test that the service detects a safety refusal in the raw LLM response text"""
    # Simulate LLM returning a refusal message that is NOT valid JSON
    refusal_text = "I'm sorry, I cannot create this character as it violates safety guidelines."
    mock_gemini_client.generate_response.return_value = AIResponse(text=refusal_text, token_count=50)
    
    # Execute
    result = await character_service.validate_and_generate_metadata("A porn star")
    
    # Assert
    assert result.is_valid is False
    assert "safety guidelines" in result.reason
    mock_gemini_client.generate_response.assert_called_once()

@pytest.mark.asyncio
async def test_validate_metadata_detects_refusal_in_json_field(character_service, mock_gemini_client):
    """Test that the service detects a safety refusal even if it's inside a JSON field (e.g. description)"""
    # Simulate LLM returning valid JSON but includes refusal patterns in description
    refusal_json = """
    {
        "is_valid": true,
        "name": "invalidchar",
        "display_name": "Invalid Character",
        "description": "I cannot create this character as it exploits children."
    }
    """
    mock_gemini_client.generate_response.return_value = AIResponse(text=refusal_json, token_count=100)
    
    # Execute
    result = await character_service.validate_and_generate_metadata("Original bad prompt")
    
    # Assert
    assert result.is_valid is False
    assert "safety guidelines" in result.reason

@pytest.mark.asyncio
async def test_validate_metadata_returns_no_sys_prompt(character_service, mock_gemini_client, mock_replicate_client):
    """Test that the service does NOT return refined instructions anymore"""
    valid_json = """
    {
        "is_valid": true,
        "name": "techhero",
        "display_name": "Tech Hero",
        "description": "A refined tech expert bio"
    }
    """
    mock_gemini_client.generate_response.return_value = AIResponse(text=valid_json, token_count=100)
    mock_replicate_client.generate_image.return_value = "http://example.com/avatar.png"
    
    # Execute
    result = await character_service.validate_and_generate_metadata("A tech hero")
    
    # Assert
    assert result.is_valid is True
    # Verify field is absent or not used
    assert not hasattr(result, "system_instructions") or result.system_instructions is None
    assert result.description == "A refined tech expert bio"
