"""
Tests for health check and status endpoints
"""
from datetime import datetime


def test_root_endpoint(client):
    """Test root endpoint returns service information"""
    response = client.get("/")
    
    assert response.status_code == 200
    data = response.json()
    
    # Verify required fields
    assert "service" in data
    assert "version" in data
    assert "status" in data
    assert "docs" in data
    assert "health" in data
    
    # Verify values
    assert data["service"] == "Yral AI Chat API"
    assert data["version"] == "1.0.0"
    assert data["status"] == "running"
    assert data["docs"] == "/docs"
    assert data["health"] == "/health"


def test_health_endpoint(client):
    """Test health check endpoint returns service statuses"""
    response = client.get("/health")
    
    assert response.status_code == 200
    data = response.json()
    
    # Verify required fields
    assert "status" in data
    assert "timestamp" in data
    assert "services" in data
    
    # Verify overall status
    assert data["status"] in ["healthy", "unhealthy"]
    
    # Verify timestamp is valid ISO format
    timestamp = datetime.fromisoformat(data["timestamp"])
    assert isinstance(timestamp, datetime)
    
    # Verify services
    services = data["services"]
    assert "database" in services
    assert "gemini_api" in services
    
    # Verify database service structure
    db_service = services["database"]
    assert "status" in db_service
    assert "latency_ms" in db_service
    assert db_service["status"] in ["up", "down"]
    
    # Verify gemini_api service structure
    gemini_service = services["gemini_api"]
    assert "status" in gemini_service
    assert "latency_ms" in gemini_service
    assert gemini_service["status"] in ["up", "down"]


def test_status_endpoint(client):
    """Test status endpoint returns system statistics"""
    response = client.get("/status")
    
    assert response.status_code == 200
    data = response.json()
    
    # Verify required fields
    assert "service" in data
    assert "version" in data
    assert "environment" in data
    assert "uptime_seconds" in data
    assert "database" in data
    assert "statistics" in data
    assert "timestamp" in data
    
    # Verify service info
    assert data["service"] == "Yral AI Chat API"
    assert data["version"] == "1.0.0"
    assert isinstance(data["uptime_seconds"], int)
    assert data["uptime_seconds"] >= 0
    
    # Verify timestamp is valid ISO format
    timestamp = datetime.fromisoformat(data["timestamp"])
    assert isinstance(timestamp, datetime)
    
    # Verify database stats
    db_stats = data["database"]
    assert "connected" in db_stats
    assert isinstance(db_stats["connected"], bool)
    
    # Verify system statistics
    stats = data["statistics"]
    assert "total_conversations" in stats
    assert "total_messages" in stats
    assert "active_influencers" in stats
    assert isinstance(stats["total_conversations"], int)
    assert isinstance(stats["total_messages"], int)
    assert isinstance(stats["active_influencers"], int)
    assert stats["total_conversations"] >= 0
    assert stats["total_messages"] >= 0
    assert stats["active_influencers"] >= 0


def test_health_endpoint_structure(client):
    """Test health endpoint response structure matches expected format"""
    response = client.get("/health")
    
    assert response.status_code == 200
    data = response.json()
    
    # Verify the response can be parsed as expected
    assert len(data) == 3  # status, timestamp, services
    assert len(data["services"]) >= 2  # at least database and gemini_api


def test_status_endpoint_environment(client):
    """Test status endpoint returns valid environment value"""
    response = client.get("/status")
    
    assert response.status_code == 200
    data = response.json()
    
    # Verify environment is one of the expected values
    assert data["environment"] in ["development", "staging", "production"]
