"""
Pytest configuration and shared fixtures for API tests

Tests use FastAPI TestClient - no separate server needed!

Note: Make sure src/config.py has media_upload_dir and media_base_url fields.
"""
import time

import jwt
import pytest
from fastapi.testclient import TestClient

from src.config import settings
from src.main import app


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
