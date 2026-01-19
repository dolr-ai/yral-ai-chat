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
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest
import requests
from dotenv import load_dotenv
from fastapi.testclient import TestClient

# Load environment variables from .env for tests
load_dotenv()

# Force single connection pool for tests to avoid SQLite disk I/O errors
# caused by file locking contention when running multiple workers
os.environ["DATABASE_POOL_SIZE"] = "1"
os.environ["DATABASE_POOL_TIMEOUT"] = "10.0"  # Fail fast in tests


@pytest.fixture(autouse=True)
def disable_sentry_during_tests(monkeypatch):
    """Explicitly disable Sentry for all tests by wiping its DSN"""
    monkeypatch.setenv("SENTRY_DSN", "")


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
def _setup_test_database():
    """
    Setup test database environment.
    
    CRITICAL: This fixture runs ONCE per test session.
    It ensures we have a clean, isolated database for testing.
    
    Safety features:
    1. Uses a unique temporary file per worker (via xdist)
    2. Wipes any existing file to prevent stale data usage
    3. Runs migrations to ensure schema matches production
    4. Fails HARD if setup encounters any error
    """
    # 1. Determine unique database path for this worker
    # 'gw0', 'gw1' etc for parallel runs, or 'master' for sequential
    worker_id = os.getenv("PYTEST_XDIST_WORKER", "master")
    temp_dir = Path(tempfile.gettempdir())
    test_db_path = str(temp_dir / f"yral_chat_test_{worker_id}.db")
    
    # 2. Set environment variable so app uses this DB
    os.environ["TEST_DATABASE_PATH"] = test_db_path
    
    # 3. Initialize Database (Skip if running against remote API)
    if not os.getenv("TEST_API_URL"):
        try:
            # SAFETY: Always start fresh. Remove old/stale DB files.
            if Path(test_db_path).exists():
                try:
                    Path(test_db_path).unlink()
                except OSError:
                    # Best effort cleanup - file might be locked by zombie process
                    pass
            
            # Execute migration script
            # We use subprocess to run it in a separate process for isolation
            migration_script = Path(__file__).parent.parent / "scripts" / "run_migrations.py"
            
            result = subprocess.run(  # noqa: S603
                [sys.executable, str(migration_script)],
                env={**os.environ, "DATABASE_PATH": test_db_path},
                capture_output=True,
                text=True,
                check=False
            )
            
            # CRITICAL: Fail setup if migrations fail.
            # Do NOT proceed with an empty or broken database.
            if result.returncode != 0:
                print(f"❌ Test Database Setup Failed!\nCMD: {result.args}\nERROR: {result.stderr}")  # noqa: T201
                raise RuntimeError("Database migration failed")  # noqa: TRY301

        except Exception as e:
            # Catch-all to ensure we don't silently skip setup failures
            print(f"❌ Fatal error in test setup: {e}")  # noqa: T201
            raise

    yield
    
    # 4. Cleanup after tests finish
    if test_db_path != ":memory:" and Path(test_db_path).exists():
        try:
            Path(test_db_path).unlink()
        except Exception:
            pass


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
        yield RemoteClient(test_api_url)
    else:
        # Local mode: use TestClient (no uvicorn needed)
        from src.main import app

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
        "/api/v1/chat/conversations", json={"influencer_id": test_influencer_id}, headers=auth_headers
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
        "/api/v1/chat/conversations", json={"influencer_id": test_influencer_id}, headers=auth_headers
    )
    assert response.status_code == 201
    conversation_id = response.json()["id"]

    yield conversation_id

    # Cleanup: Delete the conversation
    try:
        client.delete(f"/api/v1/chat/conversations/{conversation_id}", headers=auth_headers)
    except Exception:
        pass  # Ignore cleanup errors
