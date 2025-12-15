"""
Pytest configuration and shared fixtures for API tests

Tests use FastAPI TestClient - no separate server needed!

Note: Make sure src/config.py has media_upload_dir and media_base_url fields.
"""
import pytest
from fastapi.testclient import TestClient

from src.main import app


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
    """
    response = client.get("/api/v1/influencers?limit=1")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] > 0
    return data["influencers"][0]["id"]


@pytest.fixture(scope="module")
def test_conversation_id(client, test_influencer_id):
    """
    Create a test conversation and return its ID
    """
    response = client.post(
        "/api/v1/chat/conversations",
        json={"influencer_id": test_influencer_id}
    )
    assert response.status_code == 201
    data = response.json()
    return data["id"]


@pytest.fixture(scope="function")
def clean_conversation_id(client, test_influencer_id):
    """
    Create a fresh conversation for each test and clean it up after
    """
    # Create conversation
    response = client.post(
        "/api/v1/chat/conversations",
        json={"influencer_id": test_influencer_id}
    )
    assert response.status_code == 201
    conversation_id = response.json()["id"]
    
    yield conversation_id
    
    # Cleanup: Delete the conversation
    try:
        client.delete(f"/api/v1/chat/conversations/{conversation_id}")
    except Exception:
        pass  # Ignore cleanup errors
