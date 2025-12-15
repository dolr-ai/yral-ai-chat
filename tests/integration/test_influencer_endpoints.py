"""
Tests for influencer endpoints
"""
from datetime import datetime
from uuid import UUID


def test_list_influencers_default_pagination(client):
    """Test listing influencers with default pagination"""
    response = client.get("/api/v1/influencers")

    assert response.status_code == 200
    data = response.json()

    # Verify response structure
    assert "influencers" in data
    assert "total" in data
    assert "limit" in data
    assert "offset" in data

    # Verify pagination defaults
    assert data["limit"] == 50
    assert data["offset"] == 0

    # Verify we have influencers
    assert isinstance(data["influencers"], list)
    assert data["total"] > 0
    assert len(data["influencers"]) > 0


def test_list_influencers_custom_pagination(client):
    """Test listing influencers with custom limit and offset"""
    response = client.get("/api/v1/influencers?limit=2&offset=1")

    assert response.status_code == 200
    data = response.json()

    # Verify custom pagination
    assert data["limit"] == 2
    assert data["offset"] == 1
    assert len(data["influencers"]) <= 2


def test_list_influencers_response_structure(client):
    """Test influencer response contains all required fields"""
    response = client.get("/api/v1/influencers?limit=1")

    assert response.status_code == 200
    data = response.json()
    assert len(data["influencers"]) > 0

    influencer = data["influencers"][0]

    # Verify required fields
    assert "id" in influencer
    assert "name" in influencer
    assert "display_name" in influencer
    assert "avatar_url" in influencer
    assert "description" in influencer
    assert "category" in influencer
    assert "is_active" in influencer
    assert "created_at" in influencer

    # Verify data types
    assert isinstance(influencer["id"], str)
    UUID(influencer["id"])  # Validate UUID format
    assert isinstance(influencer["name"], str)
    assert isinstance(influencer["display_name"], str)
    assert isinstance(influencer["is_active"], bool)

    # Verify timestamp format
    created_at = datetime.fromisoformat(influencer["created_at"])
    assert isinstance(created_at, datetime)


def test_list_influencers_total_count_matches(client):
    """Test that total count is accurate"""
    response = client.get("/api/v1/influencers?limit=100")

    assert response.status_code == 200
    data = response.json()

    # Total should match actual count when limit is high enough
    assert data["total"] >= len(data["influencers"])


def test_get_single_influencer(client, test_influencer_id):
    """Test getting a single influencer by ID"""
    response = client.get(f"/api/v1/influencers/{test_influencer_id}")

    assert response.status_code == 200
    data = response.json()

    # Verify required fields
    assert "id" in data
    assert "name" in data
    assert "display_name" in data
    assert "avatar_url" in data
    assert "description" in data
    assert "category" in data
    assert "is_active" in data
    assert "created_at" in data
    assert "conversation_count" in data

    # Verify the ID matches
    assert data["id"] == test_influencer_id

    # Verify data types
    UUID(data["id"])
    assert isinstance(data["name"], str)
    assert isinstance(data["display_name"], str)
    assert isinstance(data["is_active"], bool)

    # Conversation count can be null or an integer
    if data["conversation_count"] is not None:
        assert isinstance(data["conversation_count"], int)
        assert data["conversation_count"] >= 0


def test_get_influencer_with_invalid_uuid(client):
    """Test getting influencer with invalid UUID format"""
    response = client.get("/api/v1/influencers/invalid-uuid-format")

    # Should return 422 validation error
    assert response.status_code == 422
    data = response.json()
    assert "error" in data
    assert data["error"] == "validation_error"
    assert "message" in data


def test_get_nonexistent_influencer(client):
    """Test getting influencer that doesn't exist"""
    fake_uuid = "00000000-0000-0000-0000-000000000000"
    response = client.get(f"/api/v1/influencers/{fake_uuid}")

    # Should return 404 not found
    assert response.status_code == 404
    data = response.json()
    assert "error" in data
    assert data["error"] == "not_found"
    assert "message" in data


def test_list_influencers_pagination_consistency(client):
    """Test pagination returns consistent results"""
    # Get first page
    response1 = client.get("/api/v1/influencers?limit=2&offset=0")
    assert response1.status_code == 200
    data1 = response1.json()

    # Get second page
    response2 = client.get("/api/v1/influencers?limit=2&offset=2")
    assert response2.status_code == 200
    data2 = response2.json()

    # Verify total is same for both requests
    assert data1["total"] == data2["total"]

    # Verify we got different influencers (if there are enough)
    if data1["total"] > 2 and len(data2["influencers"]) > 0:
        assert data1["influencers"][0]["id"] != data2["influencers"][0]["id"]
