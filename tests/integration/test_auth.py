"""
Tests for JWT authentication
"""
import time

import jwt

from src.config import settings


def generate_test_token(user_id: str = "test_user_123", expires_in_seconds: int = 3600) -> str:
    """
    Generate a properly signed test JWT token for testing.
    
    Uses HS256 with the configured secret key to create a valid token
    that will pass signature verification.

    Args:
        user_id: User ID to include in token (mapped to `sub`)
        expires_in_seconds: Token expiration time in seconds

    Returns:
        JWT token string with valid signature
    """
    now = int(time.time())

    payload = {
        "sub": user_id,
        "iss": settings.jwt_issuer,
        "iat": now,
        "exp": now + expires_in_seconds,
    }

    # Generate a properly signed token using HS256
    token = jwt.encode(
        payload,
        settings.jwt_secret_key,
        algorithm="HS256"
    )
    
    return token


def test_create_conversation_with_valid_token(client, test_influencer_id):
    """Test creating a conversation with a valid JWT token"""
    token = generate_test_token(user_id="test_user_valid")
    
    response = client.post(
        "/api/v1/chat/conversations",
        json={"influencer_id": test_influencer_id},
        headers={"Authorization": f"Bearer {token}"}
    )
    
    assert response.status_code == 201
    data = response.json()
    assert "id" in data
    assert "user_id" in data
    assert data["user_id"] == "test_user_valid"


def test_create_conversation_without_token(client, test_influencer_id):
    """Test creating a conversation without authorization header"""
    response = client.post(
        "/api/v1/chat/conversations",
        json={"influencer_id": test_influencer_id}
    )
    
    assert response.status_code == 401
    data = response.json()
    assert "detail" in data
    assert "Missing authorization header" in data["detail"]


def test_create_conversation_with_invalid_token_format(client, test_influencer_id):
    """Test creating a conversation with invalid token format"""
    # Missing "Bearer " prefix
    response = client.post(
        "/api/v1/chat/conversations",
        json={"influencer_id": test_influencer_id},
        headers={"Authorization": "invalid_token_format"}
    )
    
    assert response.status_code == 401
    data = response.json()
    assert "detail" in data
    assert "Invalid authorization header format" in data["detail"]


def test_create_conversation_with_invalid_token(client, test_influencer_id):
    """Test creating a conversation with an invalid JWT token"""
    # Malformed token that should fail decoding
    invalid_token = "invalid.token.value"

    response = client.post(
        "/api/v1/chat/conversations",
        json={"influencer_id": test_influencer_id},
        headers={"Authorization": f"Bearer {invalid_token}"}
    )
    
    assert response.status_code == 401
    data = response.json()
    assert "detail" in data
    assert "Invalid token" in data["detail"] or "Authentication failed" in data["detail"]


def test_create_conversation_with_expired_token(client, test_influencer_id):
    """Test creating a conversation with an expired JWT token"""
    # Generate an expired token (expired 1 hour ago)
    expired_token = generate_test_token(user_id="test_user", expires_in_seconds=-3600)
    
    response = client.post(
        "/api/v1/chat/conversations",
        json={"influencer_id": test_influencer_id},
        headers={"Authorization": f"Bearer {expired_token}"}
    )
    
    assert response.status_code == 401
    data = response.json()
    assert "detail" in data
    assert "expired" in data["detail"].lower() or "Token has expired" in data["detail"]


def test_create_conversation_with_wrong_issuer(client, test_influencer_id):
    """Test creating a conversation with token from wrong issuer"""
    now = int(time.time())

    # Token with wrong issuer
    wrong_issuer_payload = {
        "sub": "test_user",
        "iss": "wrong_issuer",
        "iat": now,
        "exp": now + 3600,
    }
    wrong_issuer_token = jwt.encode(
        wrong_issuer_payload,
        settings.jwt_secret_key,
        algorithm="HS256"
    )
    
    response = client.post(
        "/api/v1/chat/conversations",
        json={"influencer_id": test_influencer_id},
        headers={"Authorization": f"Bearer {wrong_issuer_token}"}
    )
    
    assert response.status_code == 401
    data = response.json()
    assert "detail" in data
    assert "issuer" in data["detail"].lower() or "Invalid token issuer" in data["detail"]


def test_create_conversation_with_missing_user_id(client, test_influencer_id):
    """Test creating a conversation with token missing sub (user identifier)"""
    now = int(time.time())

    # Token without sub
    token_without_sub_payload = {
        "iss": settings.jwt_issuer,
        "iat": now,
        "exp": now + 3600,
    }
    token_without_sub = jwt.encode(
        token_without_sub_payload,
        settings.jwt_secret_key,
        algorithm="HS256"
    )
    
    response = client.post(
        "/api/v1/chat/conversations",
        json={"influencer_id": test_influencer_id},
        headers={"Authorization": f"Bearer {token_without_sub}"}
    )
    
    assert response.status_code == 401
    data = response.json()
    assert "detail" in data
    detail_lower = data["detail"].lower()
    assert "sub" in detail_lower or "missing sub" in detail_lower


def test_send_message_with_valid_token(client, test_influencer_id):
    """Test sending a message with a valid JWT token"""
    # Use the same user_id for both creating conversation and sending message
    user_id = "test_user_valid"
    token = generate_test_token(user_id=user_id)
    
    # Create a conversation with the same user_id
    create_response = client.post(
        "/api/v1/chat/conversations",
        json={"influencer_id": test_influencer_id},
        headers={"Authorization": f"Bearer {token}"}
    )
    assert create_response.status_code == 201
    conversation_id = create_response.json()["id"]
    
    # Now send a message to that conversation with the same user_id
    response = client.post(
        f"/api/v1/chat/conversations/{conversation_id}/messages",
        json={
            "content": "Hello, this is a test message!",
            "message_type": "text"
        },
        headers={"Authorization": f"Bearer {token}"}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert "user_message" in data
    assert "assistant_message" in data
    
    # Cleanup: Delete the conversation
    try:
        client.delete(
            f"/api/v1/chat/conversations/{conversation_id}",
            headers={"Authorization": f"Bearer {token}"}
        )
    except Exception:
        pass  # Ignore cleanup errors


def test_send_message_without_token(client, clean_conversation_id):
    """Test sending a message without authorization header"""
    response = client.post(
        f"/api/v1/chat/conversations/{clean_conversation_id}/messages",
        json={
            "content": "Hello, this is a test message!",
            "message_type": "text"
        }
    )
    
    assert response.status_code == 401
    data = response.json()
    assert "detail" in data
    assert "Missing authorization header" in data["detail"]


def test_list_conversations_with_valid_token(client):
    """Test listing conversations with a valid JWT token"""
    token = generate_test_token(user_id="test_user_valid")
    
    response = client.get(
        "/api/v1/chat/conversations",
        headers={"Authorization": f"Bearer {token}"}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert "conversations" in data
    assert "total" in data


def test_list_conversations_without_token(client):
    """Test listing conversations without authorization header"""
    response = client.get("/api/v1/chat/conversations")
    
    assert response.status_code == 401
    data = response.json()
    assert "detail" in data
    assert "Missing authorization header" in data["detail"]

