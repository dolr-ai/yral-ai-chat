
import time
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from src.models.entities import MessageRole
from tests.conftest import generate_test_token


@pytest.fixture
def unique_auth_headers():
    """Generate unique auth headers for each test to ensure isolation"""
    token = generate_test_token(user_id=f"user_{int(time.time())}")
    return {"Authorization": f"Bearer {token}"}

def test_respond_first_persist_later_flow(client: TestClient, unique_auth_headers: dict, test_influencer_id: str):
    """
    Integration test to verify that messages are returned to the user
    holding to the Respond First, Persist Later principle.
    """
    # 1. Create a conversation
    resp = client.post(
        "/api/v1/chat/conversations",
        json={"influencer_id": test_influencer_id},
        headers=unique_auth_headers
    )
    # create_conversation returns 201
    assert resp.status_code in [200, 201], f"Expected 200/201, got {resp.status_code}"
    conv_id = resp.json()["id"]

    # 2. Send message
    # send_message returns 200
    response = client.post(
        f"/api/v1/chat/conversations/{conv_id}/messages",
        json={
            "message_type": "TEXT",
            "content": "Verify persistence pattern"
        },
        headers=unique_auth_headers
    )
    
    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    data = response.json()
    assert "user_message" in data
    
    # Check that messages arrived in DB (TestClient runs background tasks before returning)
    get_resp = client.get(f"/api/v1/chat/conversations/{conv_id}/messages", headers=unique_auth_headers)
    assert get_resp.status_code == 200
    messages = get_resp.json()["messages"]
    assert any(m["content"] == "Verify persistence pattern" for m in messages)

@pytest.mark.asyncio
async def test_persistence_background_task_execution():
    """
    Verify that ChatService._persist_message correctly calls the repository.
    """
    from src.services.chat_service import ChatService
    
    # Mock repositories
    msg_repo = AsyncMock()
    msg_repo.create = AsyncMock(return_value=MagicMock())
    
    # Initialize service with mocks using keyword arguments to avoid positional errors
    service = ChatService(
        gemini_client=AsyncMock(),
        influencer_repo=AsyncMock(),
        conversation_repo=AsyncMock(),
        message_repo=msg_repo
    )
    
    kwargs = {
        "conversation_id": "550e8400-e29b-41d4-a716-446655440000",
        "role": MessageRole.USER,
        "content": "Test background",
        "message_type": "text",
        "message_id_override": "msg-123"
    }

    # Execute the background task logic
    await service._persist_message(**kwargs)
    
    # Verify the sequence: _persist_message -> _save_message -> message_repo.create
    assert msg_repo.create.called

def test_send_message_returns_in_memory_data(client: TestClient, unique_auth_headers: dict, test_influencer_id: str):
    """
    Verify that the response contains data constructed in-memory.
    """
    resp = client.post("/api/v1/chat/conversations", json={"influencer_id": test_influencer_id}, headers=unique_auth_headers)
    assert resp.status_code in [200, 201]
    conv_id = resp.json()["id"]
    
    response = client.post(
        f"/api/v1/chat/conversations/{conv_id}/messages",
        json={"message_type": "TEXT", "content": "Instant response test"},
        headers=unique_auth_headers
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["user_message"]["content"] == "Instant response test"
    assert "id" in data["user_message"]
