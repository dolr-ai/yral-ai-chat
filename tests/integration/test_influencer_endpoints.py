"""
Tests for influencer endpoints
"""

from datetime import datetime

import pytest


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
    assert "starter_video_prompt" not in influencer

    # Verify data types
    assert isinstance(influencer["id"], str)
    assert isinstance(influencer["name"], str)
    assert isinstance(influencer["display_name"], str)
    assert isinstance(influencer["is_active"], str)
    assert influencer["is_active"] in ["active", "coming_soon", "discontinued"]

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
    assert "starter_video_prompt" not in data

    # Verify the ID matches
    assert data["id"] == test_influencer_id

    # Verify data types
    assert isinstance(data["name"], str)
    assert isinstance(data["display_name"], str)
    assert isinstance(data["is_active"], str)
    assert data["is_active"] in ["active", "coming_soon", "discontinued"]


def test_get_influencer_with_invalid_uuid(client):
    """Test getting influencer with an invalid ID"""
    response = client.get("/api/v1/influencers/invalid-uuid-format")

    # With non-UUID IDs allowed, an unknown ID should return 404 not found
    assert response.status_code == 404
    data = response.json()
    assert "error" in data
    assert data["error"] == "not_found"
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


def test_update_system_prompt_success(client):
    """Test updating system prompt as bot owner"""
    from tests.conftest import generate_test_token
    
    # Create a test influencer with a specific owner
    owner_user_id = "test_owner_user_123"
    token = generate_test_token(user_id=owner_user_id)
    auth_headers = {"Authorization": f"Bearer {token}"}
    
    # Create an influencer owned by this user
    create_response = client.post(
        "/api/v1/influencers/create",
        json={
            "bot_principal_id": "test-bot-123",
            "parent_principal_id": owner_user_id,
            "name": "test_bot",
            "display_name": "Test Bot",
            "description": "A test bot for system prompt updates",
            "system_instructions": "You are a helpful assistant.",
            "category": "general",
            "avatar_url": "https://example.com/avatar.jpg",
            "initial_greeting": "Hello!",
            "suggested_messages": ["Tell me a joke"],
            "personality_traits": {"friendly": True},
        },
        headers=auth_headers,
    )
    
    # If creation fails (e.g., duplicate ID), try with a different ID
    if create_response.status_code != 200:
        import time
        unique_id = f"test-bot-{int(time.time())}"
        create_response = client.post(
            "/api/v1/influencers/create",
            json={
                "bot_principal_id": unique_id,
                "parent_principal_id": owner_user_id,
                "name": f"test_bot_{int(time.time())}",
                "display_name": "Test Bot",
                "description": "A test bot for system prompt updates",
                "system_instructions": "You are a helpful assistant.",
                "category": "general",
                "avatar_url": "https://example.com/avatar.jpg",
                "initial_greeting": "Hello!",
                "suggested_messages": ["Tell me a joke"],
                "personality_traits": {"friendly": True},
            },
            headers=auth_headers,
        )
    
    assert create_response.status_code == 200
    created_influencer = create_response.json()
    influencer_id = created_influencer["id"]
    
    # Update the system prompt
    new_prompt = "You are a helpful AI assistant with updated instructions."
    response = client.patch(
        f"/api/v1/influencers/{influencer_id}/system-prompt",
        json={"system_instructions": new_prompt},
        headers=auth_headers,
    )
    
    assert response.status_code == 200
    data = response.json()
    
    # Verify response structure
    assert "id" in data
    assert data["id"] == influencer_id
    assert "name" in data
    assert "display_name" in data


def test_update_system_prompt_unauthorized(client):
    """Test updating system prompt without authentication"""
    response = client.patch(
        "/api/v1/influencers/some-influencer-id/system-prompt",
        json={"system_instructions": "New prompt"},
    )
    
    assert response.status_code == 401
    data = response.json()
    assert "detail" in data


def test_update_system_prompt_forbidden(client):
    """Test updating system prompt as non-owner"""
    from tests.conftest import generate_test_token
    
    # Create an influencer owned by one user
    owner_user_id = "original_owner_456"
    owner_token = generate_test_token(user_id=owner_user_id)
    owner_headers = {"Authorization": f"Bearer {owner_token}"}
    
    import time
    unique_id = f"test-bot-forbidden-{int(time.time())}"
    
    create_response = client.post(
        "/api/v1/influencers/create",
        json={
            "bot_principal_id": unique_id,
            "parent_principal_id": owner_user_id,
            "name": f"test_bot_forbidden_{int(time.time())}",
            "display_name": "Test Bot for Forbidden",
            "description": "A test bot for forbidden access",
            "system_instructions": "You are a helpful assistant.",
            "category": "general",
            "avatar_url": "https://example.com/avatar.jpg",
            "initial_greeting": "Hello!",
            "suggested_messages": ["Tell me a joke"],
            "personality_traits": {"friendly": True},
        },
        headers=owner_headers,
    )
    
    assert create_response.status_code == 200
    created_influencer = create_response.json()
    influencer_id = created_influencer["id"]
    
    # Use a different user ID (not the owner)
    different_user_id = "different_user_789"
    token = generate_test_token(user_id=different_user_id)
    auth_headers = {"Authorization": f"Bearer {token}"}
    
    # Try to update the system prompt
    response = client.patch(
        f"/api/v1/influencers/{influencer_id}/system-prompt",
        json={"system_instructions": "Unauthorized update attempt"},
        headers=auth_headers,
    )
    
    assert response.status_code == 403
    data = response.json()
    assert "detail" in data
    assert "bot owner" in data["detail"].lower()


def test_update_system_prompt_not_found(client, auth_headers):
    """Test updating system prompt for non-existent influencer"""
    fake_id = "non-existent-influencer-id"
    
    response = client.patch(
        f"/api/v1/influencers/{fake_id}/system-prompt",
        json={"system_instructions": "New prompt"},
        headers=auth_headers,
    )
    
    assert response.status_code == 404
    data = response.json()
    assert "error" in data
    assert data["error"] == "not_found"


def test_update_system_prompt_validation_error(client):
    """Test updating system prompt with invalid data"""
    from tests.conftest import generate_test_token
    
    token = generate_test_token(user_id="test_user")
    auth_headers = {"Authorization": f"Bearer {token}"}
    
    # Try to update with empty system_instructions
    response = client.patch(
        "/api/v1/influencers/some-id/system-prompt",
        json={"system_instructions": ""},
        headers=auth_headers,
    )
    
    assert response.status_code == 422  # Validation error


def test_delete_influencer_success(client):
    """Test soft deleting an influencer as bot owner"""
    from tests.conftest import generate_test_token
    
    # Create a test influencer
    owner_user_id = "delete_test_owner_123"
    token = generate_test_token(user_id=owner_user_id)
    auth_headers = {"Authorization": f"Bearer {token}"}
    
    import time
    unique_id = f"test-bot-delete-{int(time.time())}"
    
    create_response = client.post(
        "/api/v1/influencers/create",
        json={
            "bot_principal_id": unique_id,
            "parent_principal_id": owner_user_id,
            "name": f"test_bot_delete_{int(time.time())}",
            "display_name": "Test Bot to Delete",
            "description": "A test bot for deletion",
            "system_instructions": "You are a helpful assistant.",
            "category": "general",
            "avatar_url": "https://example.com/avatar.jpg",
            "initial_greeting": "Hello!",
            "suggested_messages": ["Tell me a joke"],
            "personality_traits": {"friendly": True},
        },
        headers=auth_headers,
    )
    
    assert create_response.status_code == 200
    created_influencer = create_response.json()
    influencer_id = created_influencer["id"]
    
    # Soft delete the influencer
    response = client.delete(
        f"/api/v1/influencers/{influencer_id}",
        headers=auth_headers,
    )
    
    assert response.status_code == 200
    data = response.json()
    
    # Verify soft delete behavior
    assert data["id"] == influencer_id
    assert data["display_name"] == "Deleted Bot"
    assert data["is_active"] == "discontinued"


def test_delete_influencer_unauthorized(client):
    """Test deleting influencer without authentication"""
    response = client.delete("/api/v1/influencers/some-influencer-id")
    
    assert response.status_code == 401
    data = response.json()
    assert "detail" in data


def test_delete_influencer_forbidden(client):
    """Test deleting influencer as non-owner"""
    from tests.conftest import generate_test_token
    
    # Create an influencer owned by one user
    owner_user_id = "delete_owner_456"
    owner_token = generate_test_token(user_id=owner_user_id)
    owner_headers = {"Authorization": f"Bearer {owner_token}"}
    
    import time
    unique_id = f"test-bot-delete-forbidden-{int(time.time())}"
    
    create_response = client.post(
        "/api/v1/influencers/create",
        json={
            "bot_principal_id": unique_id,
            "parent_principal_id": owner_user_id,
            "name": f"test_bot_delete_forbidden_{int(time.time())}",
            "display_name": "Test Bot for Forbidden Delete",
            "description": "A test bot for forbidden deletion",
            "system_instructions": "You are a helpful assistant.",
            "category": "general",
            "avatar_url": "https://example.com/avatar.jpg",
            "initial_greeting": "Hello!",
            "suggested_messages": ["Tell me a joke"],
            "personality_traits": {"friendly": True},
        },
        headers=owner_headers,
    )
    
    assert create_response.status_code == 200
    created_influencer = create_response.json()
    influencer_id = created_influencer["id"]
    
    # Try to delete as a different user
    different_user_id = "different_delete_user_789"
    token = generate_test_token(user_id=different_user_id)
    auth_headers = {"Authorization": f"Bearer {token}"}
    
    response = client.delete(
        f"/api/v1/influencers/{influencer_id}",
        headers=auth_headers,
    )
    
    assert response.status_code == 403
    data = response.json()
    assert "detail" in data
    assert "bot owner" in data["detail"].lower()


def test_delete_influencer_not_found(client, auth_headers):
    """Test deleting non-existent influencer"""
    fake_id = "non-existent-influencer-id"
    
    response = client.delete(
        f"/api/v1/influencers/{fake_id}",
        headers=auth_headers,
    )
    
    assert response.status_code == 404
    data = response.json()
    assert "error" in data
    assert data["error"] == "not_found"


