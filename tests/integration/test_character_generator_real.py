"""
Integration test for Character Generator using real Replicate client.
"""

import json
import os
from unittest.mock import AsyncMock

import pytest

from src.core.dependencies import get_gemini_client
from src.main import app
from src.models.internal import AIResponse


@pytest.fixture
def mock_gemini():
    return AsyncMock()


@pytest.fixture(autouse=True)
def setup_overrides(mock_gemini):
    """
    Override ONLY Gemini client, leaving Replicate client to use the real implementation.
    """
    app.dependency_overrides[get_gemini_client] = lambda: mock_gemini
    # Do NOT override get_replicate_client
    yield
    app.dependency_overrides.clear()



def test_validate_metadata_with_real_replicate(client, mock_gemini, auth_headers):
    """
    Test validation and metadata generation using REAL Replicate API for image generation.
    Gemini is mocked to ensure deterministic metadata input for Replicate.
    """
    if not os.environ.get("REPLICATE_API_TOKEN"):
        pytest.fail("REPLICATE_API_TOKEN not set in environment")
    
    # Define a character concept that should produce a valid image prompt
    system_instructions = "You are a friendly futuristic robot helper."
    
    # Mock Gemini response to return a valid JSON with an image prompt
    mock_metadata = {
        "is_valid": True,
        "name": "robo_helper",
        "display_name": "RoboHelper",
        "description": "A helpful robot for your daily tasks.",
        "initial_greeting": "Hello! How can I assist you today?",
        "suggested_messages": ["What is the weather?", "Set a timer."],
        "personality_traits": [{"trait": "helpfulness", "value": "high"}, {"trait": "humor", "value": "medium"}],
        "category": "Assistant",
        "image_prompt": "A cute, shiny, white futuristic robot with glowing blue eyes, portrait, high quality"
    }
    
    # Configure mock
    mock_gemini.generate_response.return_value = AIResponse(
        text=json.dumps(mock_metadata),
        token_count=150
    )

    # Call the endpoint
    response = client.post(
        "/api/v1/influencers/validate-and-generate-metadata",
        json={"system_instructions": system_instructions},
        headers=auth_headers
    )

    # Assertions
    assert response.status_code == 200
    data = response.json()
    
    # Verify basic metadata
    assert data["is_valid"] is True
    assert data["name"] == "robo_helper"
    assert data["display_name"] == "RoboHelper"
    
    # Verify Avatar URL generation (the real Replicate call result)
    assert "avatar_url" in data
    avatar_url = data["avatar_url"]
    
    # Since we are using the real API, we expect a valid URL string
    assert isinstance(avatar_url, str)
    assert avatar_url.startswith("http")
    

