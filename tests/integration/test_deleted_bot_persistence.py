import pytest
from src.models.entities import AIInfluencer, InfluencerStatus
from datetime import datetime, UTC

@pytest.mark.asyncio
async def test_deleted_influencer_persistence(client):
    """Test that soft-deleted influencers do not appear in lists, even with caching"""
    from tests.conftest import generate_test_token
    
    # 1. Create a bot owner
    owner_user_id = "test_owner_persistence"
    token = generate_test_token(user_id=owner_user_id)
    auth_headers = {"Authorization": f"Bearer {token}"}
    
    bot_name = "persistencebot"
    influencer_data = {
        "bot_principal_id": "test-bot-persistence",
        "parent_principal_id": owner_user_id,
        "name": bot_name,
        "display_name": "Persistence Bot",
        "description": "Test bot for persistence",
        "system_instructions": "You are a test bot.",
        "category": "test",
        "avatar_url": "https://example.com/avatar.jpg",
    }

    # 2. Create the influencer
    resp = client.post("/api/v1/influencers/create", json=influencer_data, headers=auth_headers)
    assert resp.status_code == 200
    influencer_id = resp.json()["id"]

    # 3. List influencers (this should populate the cache)
    resp = client.get("/api/v1/influencers")
    assert resp.status_code == 200
    influencers = resp.json()["influencers"]
    assert any(inf["id"] == influencer_id for inf in influencers)
    
    # 4. Success check: Details fetch
    resp = client.get(f"/api/v1/influencers/{influencer_id}")
    assert resp.status_code == 200
    assert resp.json()["display_name"] == "Persistence Bot"

    # 5. Soft delete the influencer
    resp = client.delete(f"/api/v1/influencers/{influencer_id}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["display_name"] == "Deleted Bot"
    assert resp.json()["is_active"] == "discontinued"

    # 6. List influencers again (cache should be invalidated)
    resp = client.get("/api/v1/influencers")
    assert resp.status_code == 200
    influencers = resp.json()["influencers"]
    
    # The deleted bot should NOT be in the list
    assert not any(inf["id"] == influencer_id for inf in influencers), "Deleted bot still in list!"

    # 7. Check detail fetch (Service's get_influencer filters out discontinued, so 404 is EXPECTED here)
    resp = client.get(f"/api/v1/influencers/{influencer_id}")
    assert resp.status_code == 404

    # 8. Check conversation creation (ChatService.create_conversation NOW filters, so this will 404)
    resp = client.post("/api/v1/chat/conversations", json={"influencer_id": influencer_id}, headers=auth_headers)
    assert resp.status_code == 404
