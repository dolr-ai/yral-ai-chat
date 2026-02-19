"""
Tests for security enhancements (Authentication and WebSocket protection)
"""

import pytest
from fastapi import WebSocketDisconnect
from starlette.testclient import WebSocketDenialResponse

from tests.conftest import generate_test_token


def test_create_influencer_unauthorized(client):
    """Test creating an influencer without authentication"""
    response = client.post(
        "/api/v1/influencers/create",
        json={
            "bot_principal_id": "unauth-bot",
            "name": "unauthbot",
            "display_name": "Unauth Bot",
            "system_instructions": "You are unauthorized.",
            "category": "test",
        },
    )
    assert response.status_code == 401


def test_generate_prompt_unauthorized(client):
    """Test generating a prompt without authentication"""
    response = client.post(
        "/api/v1/influencers/generate-prompt",
        json={"prompt": "A character concept"},
    )
    assert response.status_code == 401


def test_validate_metadata_unauthorized(client):
    """Test validating metadata without authentication"""
    response = client.post(
        "/api/v1/influencers/validate-and-generate-metadata",
        json={"system_instructions": "Some instructions"},
    )
    assert response.status_code == 401


def test_create_influencer_parent_id_override(client):
    """Test that parent_principal_id is overridden by authenticated user_id"""
    user_id = "real_user_id_123"
    token = generate_test_token(user_id=user_id)
    auth_headers = {"Authorization": f"Bearer {token}"}
    
    response = client.post(
        "/api/v1/influencers/create",
        json={
            "bot_principal_id": "bot-override-test",
            "parent_principal_id": "fake_parent_id",
            "name": "overridebot",
            "display_name": "Override Bot",
            "description": "Bot to test parent_id override",
            "system_instructions": "You are a test bot.",
            "category": "test",
            "avatar_url": "https://example.com/avatar.jpg",
            "initial_greeting": "Hello",
            "suggested_messages": ["Hi"],
            "personality_traits": {},
        },
        headers=auth_headers,
    )
    
    assert response.status_code == 200
    data = response.json()
    # The parent_principal_id should be the one from the token, not the request
    assert data["parent_principal_id"] == user_id


def test_websocket_unauthorized_missing_token(client):
    """Test WebSocket connection without a token"""
    # TestClient raises WebSocketDenialResponse if handshake fails with 401
    with pytest.raises(WebSocketDenialResponse) as excinfo, \
         client.websocket_connect("/api/v1/chat/ws/inbox/user123"):
        pass
    assert excinfo.value.status_code == 401


def test_websocket_unauthorized_invalid_token(client):
    """Test WebSocket connection with an invalid token"""
    with pytest.raises(WebSocketDenialResponse) as excinfo, \
         client.websocket_connect("/api/v1/chat/ws/inbox/user123?token=invalid-token"):
        pass
    assert excinfo.value.status_code == 401


def test_websocket_forbidden_wrong_user(client):
    """Test WebSocket connection where token user_id doesn't match path user_id"""
    token = generate_test_token(user_id="user456")
    with pytest.raises(WebSocketDisconnect) as excinfo, \
         client.websocket_connect(f"/api/v1/chat/ws/inbox/user123?token={token}"):
        pass
    assert excinfo.value.code == 4003


def test_websocket_authorized_success(client):
    """Test successful WebSocket connection with valid token matching user_id"""
    user_id = "user123"
    token = generate_test_token(user_id=user_id)
    with client.websocket_connect(f"/api/v1/chat/ws/inbox/{user_id}?token={token}") as websocket:
        # Connection should stay open
        try:
            # Just send/receive something to ensure it's alive
            websocket.send_text("ping")
        except Exception as e:
            pytest.fail(f"WebSocket connection failed: {e}")
