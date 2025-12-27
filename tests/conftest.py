"""
Pytest configuration and shared fixtures for API tests

Tests use FastAPI TestClient - no separate server needed!

Note: Make sure src/config.py has media_upload_dir and media_base_url fields.
"""
import base64
import json
import time

import pytest
from fastapi.testclient import TestClient

from src.main import app


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


@pytest.fixture(scope="module")
def auth_headers():
    """
    Generate authentication headers with a valid test token
    """
    token = generate_test_token(user_id="test_user_default")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def client():
    """
    FastAPI TestClient - works like HTTP client but doesn't need a server
    """
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(scope="module")
def test_influencer_id(client):
    """
    Get a valid influencer ID from the API for testing
    Note: Influencers endpoint doesn't require authentication
    """
    response = client.get("/api/v1/influencers?limit=1")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] > 0
    return data["influencers"][0]["id"]


@pytest.fixture(scope="module")
def test_conversation_id(client, test_influencer_id, auth_headers):
    """
    Create a test conversation and return its ID
    """
    response = client.post(
        "/api/v1/chat/conversations",
        json={"influencer_id": test_influencer_id},
        headers=auth_headers
    )
    assert response.status_code == 201
    data = response.json()
    return data["id"]


@pytest.fixture(scope="function")
def clean_conversation_id(client, test_influencer_id, auth_headers):
    """
    Create a fresh conversation for each test and clean it up after
    """
    # Create conversation
    response = client.post(
        "/api/v1/chat/conversations",
        json={"influencer_id": test_influencer_id},
        headers=auth_headers
    )
    assert response.status_code == 201
    conversation_id = response.json()["id"]

    yield conversation_id

    # Cleanup: Delete the conversation
    try:
        client.delete(f"/api/v1/chat/conversations/{conversation_id}", headers=auth_headers)
    except Exception:
        pass  # Ignore cleanup errors
