"""
Tests for JWT authentication
"""

import base64
import json
import time


def _encode_jwt(payload: dict) -> str:
    """Create a dummy ES256-style JWT without real signature verification."""
    header = {
        "typ": "JWT",
        "alg": "ES256",
        "kid": "default",
    }

    def b64url(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")

    header_b64 = b64url(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    payload_b64 = b64url(json.dumps(payload, separators=(",", ":")).encode("utf-8"))

    # Signature is not validated in the backend, so we can use any placeholder
    signature_b64 = "dummy_signature"

    return f"{header_b64}.{payload_b64}.{signature_b64}"


def generate_test_token(user_id: str = "test_user_123", expires_in_seconds: int = 3600) -> str:
    """
    Generate a test JWT token for testing

    Args:
        user_id: User ID to include in token (mapped to `sub`)
        expires_in_seconds: Token expiration time in seconds

    Returns:
        JWT token string
    """
    now = int(time.time())

    payload = {
        "sub": user_id,
        "iss": "https://auth.yral.com",
        "iat": now,
        "exp": now + expires_in_seconds,
    }

    return _encode_jwt(payload)


def test_create_conversation_with_valid_token(client, test_influencer_id):
    """Test creating a conversation with a valid JWT token"""
    token = generate_test_token(user_id="test_user_valid")

    response = client.post(
        "/api/v1/chat/conversations",
        json={"influencer_id": test_influencer_id},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 201
    data = response.json()
    assert "id" in data
    assert "user_id" in data
    assert data["user_id"] == "test_user_valid"


def test_create_conversation_without_token(client, test_influencer_id):
    """Test creating a conversation without authorization header"""
    response = client.post("/api/v1/chat/conversations", json={"influencer_id": test_influencer_id})

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
        headers={"Authorization": "invalid_token_format"},
    )

    assert response.status_code == 401
    data = response.json()
    assert "detail" in data
    assert "Invalid authorization header format" in data["detail"]


def test_create_conversation_with_invalid_token(client, test_influencer_id):
    """Test creating a conversation with an invalid JWT token"""
    # Malformed token that should fail decoding
    # Note: This is a test token, not a real password/secret
    invalid_token = "invalid.token.value"  # noqa: S105

    response = client.post(
        "/api/v1/chat/conversations",
        json={"influencer_id": test_influencer_id},
        headers={"Authorization": f"Bearer {invalid_token}"},
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
        headers={"Authorization": f"Bearer {expired_token}"},
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
    wrong_issuer_token = _encode_jwt(wrong_issuer_payload)

    response = client.post(
        "/api/v1/chat/conversations",
        json={"influencer_id": test_influencer_id},
        headers={"Authorization": f"Bearer {wrong_issuer_token}"},
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
        "iss": "https://auth.yral.com",
        "iat": now,
        "exp": now + 3600,
    }
    token_without_sub = _encode_jwt(token_without_sub_payload)

    response = client.post(
        "/api/v1/chat/conversations",
        json={"influencer_id": test_influencer_id},
        headers={"Authorization": f"Bearer {token_without_sub}"},
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
        headers={"Authorization": f"Bearer {token}"},
    )
    assert create_response.status_code == 201
    conversation_id = create_response.json()["id"]

    # Now send a message to that conversation with the same user_id
    response = client.post(
        f"/api/v1/chat/conversations/{conversation_id}/messages",
        json={"content": "Hello, this is a test message!", "message_type": "text"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert "user_message" in data
    assert "assistant_message" in data


def test_send_message_without_token(client, clean_conversation_id):
    """Test sending a message without authorization header"""
    response = client.post(
        f"/api/v1/chat/conversations/{clean_conversation_id}/messages",
        json={"content": "Hello, this is a test message!", "message_type": "text"},
    )

    assert response.status_code == 401
    data = response.json()
    assert "detail" in data
    assert "Missing authorization header" in data["detail"]


def test_list_conversations_with_valid_token(client):
    """Test listing conversations with a valid JWT token"""
    token = generate_test_token(user_id="test_user_valid")

    response = client.get("/api/v1/chat/conversations", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    data = response.json()
    assert "conversations" in data
    assert isinstance(data["conversations"], list)


def test_list_conversations_without_token(client):
    """Test listing conversations without authorization header"""
    response = client.get("/api/v1/chat/conversations")

    assert response.status_code == 401
    data = response.json()
    assert "detail" in data
    assert "Missing authorization header" in data["detail"]
