
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from src.db.base import DatabaseConnectionPoolTimeoutError, db
from src.main import app

client = TestClient(app)

@pytest.mark.asyncio
async def test_database_timeout_returns_503():
    """
    GIVEN the database pool throws a timeout error
    WHEN a database-dependent API request is made
    THEN the server should return a 503 Service Unavailable with a Retry-After header
    """
    await db.connect()
    
    # We patch the fetch method of the db object used by the repository
    with patch("src.db.repositories.influencer_repository.db.fetch", side_effect=DatabaseConnectionPoolTimeoutError("Pool timeout")):
        # Call an endpoint that requires database access
        response = client.get("/api/v1/influencers")
        
        assert response.status_code == 503
        data = response.json()
        assert data["error"] == "service_unavailable"
        assert "Retry-After" in response.headers
        assert response.headers["Retry-After"] == "5"
    
    await db.disconnect()
