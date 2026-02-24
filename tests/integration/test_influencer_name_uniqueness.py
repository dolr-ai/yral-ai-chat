import pytest


@pytest.mark.asyncio
async def test_create_influencer_duplicate_name(client):
    """Test that creating an influencer with an existing name returns 409 Conflict"""
    from tests.conftest import generate_test_token
    
    # Generate test user token
    owner_user_id = "test_owner_duplicate_123"
    token = generate_test_token(user_id=owner_user_id)
    auth_headers = {"Authorization": f"Bearer {token}"}
    
    influencer_data = {
        "bot_principal_id": "test-bot-duplicate-1",
        "parent_principal_id": owner_user_id,
        "name": "duplicatebot",
        "display_name": "Duplicate Bot",
        "description": "A test bot for duplicate name",
        "system_instructions": "You are a helpful assistant.",
        "category": "general",
        "avatar_url": "https://example.com/avatar.jpg",
        "initial_greeting": "Hello!",
        "suggested_messages": ["Tell me a joke"],
        "personality_traits": {"friendly": True},
    }

    # 1. First creation should succeed
    response_1 = client.post(
        "/api/v1/influencers/create",
        json=influencer_data,
        headers=auth_headers,
    )
    
    assert response_1.status_code == 200
    created_influencer = response_1.json()
    assert created_influencer["name"] == "duplicatebot"

    # 2. Change the bot_principal_id but keep the same 'name'
    influencer_data["bot_principal_id"] = "test-bot-duplicate-2"

    # 3. Second creation should fail with 409 Conflict
    response_2 = client.post(
        "/api/v1/influencers/create",
        json=influencer_data,
        headers=auth_headers,
    )
    
    assert response_2.status_code == 409
    error_data = response_2.json()
    assert "error" in error_data
    assert error_data["error"] == "conflict"
    assert "already exists" in error_data["message"].lower()
