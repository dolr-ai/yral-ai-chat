"""
Pytest configuration and shared fixtures for API tests

Tests can run in two modes:
1. Local mode (default): Uses FastAPI TestClient - no separate server needed!
2. Remote mode: Tests against staging/prod URLs via HTTP client

Set TEST_API_URL environment variable to test against remote APIs:
  TEST_API_URL=https://prod.example.com pytest

Note: Make sure src/config.py has media_upload_dir and media_base_url fields.
"""
import base64
import json
import os
import time
from pathlib import Path

import pytest
import requests
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


class RemoteClient:
    """HTTP client wrapper for testing remote APIs - compatible with TestClient interface"""
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
    
    def get(self, path: str, **kwargs):
        """GET request - returns requests.Response (compatible with TestClient)"""
        return self.session.get(f"{self.base_url}{path}", **kwargs)
    
    def post(self, path: str, **kwargs):
        """POST request - returns requests.Response (compatible with TestClient)"""
        return self.session.post(f"{self.base_url}{path}", **kwargs)
    
    def put(self, path: str, **kwargs):
        """PUT request - returns requests.Response (compatible with TestClient)"""
        return self.session.put(f"{self.base_url}{path}", **kwargs)
    
    def delete(self, path: str, **kwargs):
        """DELETE request - returns requests.Response (compatible with TestClient)"""
        return self.session.delete(f"{self.base_url}{path}", **kwargs)
    
    def patch(self, path: str, **kwargs):
        """PATCH request - returns requests.Response (compatible with TestClient)"""
        return self.session.patch(f"{self.base_url}{path}", **kwargs)


@pytest.fixture(scope="session", autouse=True)
def ensure_database_migrated():
    """
    Ensure database is migrated before running tests.
    This runs once per test session.
    """
    import subprocess
    import sys
    
    # Get database path from environment or config
    db_path = os.getenv("DATABASE_PATH")
    if not db_path:
        from src.config import settings
        db_path = settings.database_path
    
    # Only run migrations if using local database (not remote API)
    if not os.getenv("TEST_API_URL") and db_path and Path(db_path).exists():
        # Check if database has tables
        import sqlite3
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='ai_influencers'"
            )
            has_tables = cursor.fetchone() is not None
            conn.close()
            
            if not has_tables:
                print(f"\n⚠️  Database {db_path} has no tables. Running migrations...")
                result = subprocess.run(
                    [sys.executable, "scripts/run_migrations.py"],
                    env={**os.environ, "DATABASE_PATH": db_path},
                    capture_output=True,
                    text=True, check=False
                )
                if result.returncode != 0:
                    print(f"❌ Migration failed: {result.stderr}")
                else:
                    print("✅ Migrations completed")
        except Exception as e:
            print(f"⚠️  Could not check database: {e}")


@pytest.fixture(scope="module")
def client():
    """
    Client fixture - supports both local (TestClient) and remote (HTTP) testing
    
    Set TEST_API_URL environment variable to test against remote APIs:
      TEST_API_URL=https://staging.example.com pytest
    """
    test_api_url = os.getenv("TEST_API_URL")
    
    if test_api_url:
        # Remote mode: test against staging/prod
        print(f"🌐 Testing against remote API: {test_api_url}")
        yield RemoteClient(test_api_url)
    else:
        # Local mode: use TestClient (no uvicorn needed)
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
