"""
Integration tests for character creation flow
"""

import json
from unittest.mock import AsyncMock

import pytest

from src.core.dependencies import get_gemini_client, get_replicate_client
from src.main import app
from src.models.internal import AIResponse


@pytest.fixture
def mock_gemini():
    return AsyncMock()


@pytest.fixture
def mock_replicate():
    return AsyncMock()


@pytest.fixture(autouse=True)
def setup_overrides(mock_gemini, mock_replicate):
    """Setup dependency overrides for integration tests"""
    app.dependency_overrides[get_gemini_client] = lambda: mock_gemini
    app.dependency_overrides[get_replicate_client] = lambda: mock_replicate
    yield
    app.dependency_overrides.clear()


def test_character_creation_end_to_end(client, mock_gemini, mock_replicate):
    """
    Test the full character creation flow:
    1. Generate Prompt
    2. Validate & Generate Metadata
    3. Create
    4. Retrieve
    """

    # --- Step 1: Generate Prompt ---
    mock_gemini.generate_response.return_value = AIResponse(text="You are a master hacker named Neo.", token_count=100)

    response = client.post("/api/v1/influencers/generate-prompt", json={"prompt": "cyberpunk hacker"})
    assert response.status_code == 200
    data = response.json()
    assert "system_instructions" in data
    system_instructions = data["system_instructions"]
    assert "Neo" in system_instructions

    # --- Step 2: Validate & Generate Metadata ---
    mock_metadata = {
        "is_valid": True,
        "name": "neohacker",
        "display_name": "Neo",
        "description": "The One",
        "initial_greeting": "Wake up, Neo.",
        "suggested_messages": ["Follow the white rabbit"],
        "personality_traits": [{"trait": "coding", "value": "expert"}],
        "category": "Sci-Fi",
        "image_prompt": "Neo hacker portrait",
    }
    mock_gemini.generate_response.return_value = AIResponse(text=json.dumps(mock_metadata), token_count=150)
    mock_replicate.generate_image.return_value = "https://example.com/neo.jpg"

    response = client.post(
        "/api/v1/influencers/validate-and-generate-metadata", json={"system_instructions": system_instructions}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["is_valid"] is True
    assert data["name"] == "neohacker"
    assert data["avatar_url"] == "https://example.com/neo.jpg"
    assert "system_instructions" not in data

    # --- Step 3: Create ---
    create_req = {
        "name": data["name"],
        "display_name": data["display_name"],
        "description": data["description"],
        "system_instructions": system_instructions,  # Use the instructions from Step 1
        "initial_greeting": data["initial_greeting"],
        "suggested_messages": data["suggested_messages"],
        "personality_traits": data["personality_traits"],
        "category": data["category"],
        "avatar_url": data["avatar_url"],
        "is_nsfw": False,
        "bot_principal_id": "neo-principal-id",
        "parent_principal_id": "creator-principal-id",
    }

    response = client.post("/api/v1/influencers/create", json=create_req)
    assert response.status_code == 200
    created_data = response.json()
    assert created_data["name"] == "neohacker"
    assert "starter_video_prompt" in created_data
    assert isinstance(created_data["starter_video_prompt"], str)
    influencer_id = created_data["id"]

    # --- Step 4: Retrieve ---
    response = client.get(f"/api/v1/influencers/{influencer_id}")
    assert response.status_code == 200
    retrieved_data = response.json()
    assert retrieved_data["id"] == influencer_id
    assert retrieved_data["display_name"] == "Neo"
    assert "starter_video_prompt" not in retrieved_data


def test_character_creation_nsfw_rejection(client, mock_gemini):
    """Test that NSFW content is rejected during validation step"""

    mock_nsfw_response = {"is_valid": False, "reason": "NSFW content detected"}
    mock_gemini.generate_response.return_value = AIResponse(text=json.dumps(mock_nsfw_response), token_count=50)

    response = client.post(
        "/api/v1/influencers/validate-and-generate-metadata", json={"system_instructions": "Some NSFW instructions..."}
    )
    assert response.status_code == 200  # API returns 200 but is_valid is False
    data = response.json()
    assert data["is_valid"] is False
    assert "NSFW" in data["reason"]
