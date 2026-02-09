"""
Integration test for starting message generation on bot creation
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


def test_create_influencer_generates_starting_message(client, mock_gemini, mock_replicate, auth_headers):
    """
    Test that creating an influencer without an initial greeting
    causes the system to generate one using the AI.
    """

    # Mock response for generate_initial_greeting
    mock_greeting_data = {
        "initial_greeting": "Namaste! I am your AI Guru.",
        "suggested_messages": ["How do I meditate?", "Tell me a quote"]
    }
    
    # mock_gemini will be called for initial greeting generation
    mock_gemini.generate_response.return_value = AIResponse(
        text=json.dumps(mock_greeting_data),
        token_count=100
    )

    create_req = {
        "name": "aiguru",
        "display_name": "AI Guru",
        "description": "Spiritual guide",
        "system_instructions": "You are a spiritual guide.",
        "initial_greeting": None,  # Explicitly None to trigger generation
        "suggested_messages": [],   # Empty to trigger generation
        "personality_traits": {"calm": "high"},
        "category": "Spirituality",
        "avatar_url": None,
        "is_nsfw": False,
        "bot_principal_id": "guru-principal-id",
        "parent_principal_id": "creator-principal-id",
    }

    response = client.post("/api/v1/influencers/create", json=create_req)
    assert response.status_code == 200
    data = response.json()
    
    # Verify the generated greeting and suggestions are NOT in the response (as per user request)
    assert "initial_greeting" not in data
    assert "suggested_messages" not in data
    
    influencer_id = data["id"]

    # Verify they were also stored (by checking a new conversation)
    conv_req = {"influencer_id": influencer_id}
    
    response = client.post("/api/v1/chat/conversations", json=conv_req, headers=auth_headers)
    assert response.status_code in {200, 201}
    conv_id = response.json()["id"]
    
    # Check messages in the conversation
    response = client.get(f"/api/v1/chat/conversations/{conv_id}/messages", headers=auth_headers)
    assert response.status_code == 200
    msg_data = response.json()
    
    # The first message should be the assistant's initial greeting
    messages = msg_data["messages"]
    assert len(messages) >= 1
    # Find the assistant message
    assistant_msgs = [m for m in messages if m["role"] == "assistant"]
    assert len(assistant_msgs) == 1
    assert assistant_msgs[0]["content"] == "Namaste! I am your AI Guru."
