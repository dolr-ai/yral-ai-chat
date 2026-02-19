import time

import pytest

from tests.conftest import generate_test_token


@pytest.mark.asyncio
async def test_trending_influencers_sorting(client, auth_headers):
    """Test that influencers are sorted by message count on the trending endpoint"""
    unique_suffix = int(time.time() * 10) % 10**8
    
    # 1. Create two bots
    bots = []
    for i in range(2):
        owner_id = f"u{unique_suffix}{i}"
        bot_id = f"b{unique_suffix}{i}"
        bot_name = f"n{unique_suffix}{i}"
        token = generate_test_token(user_id=owner_id)
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        
        create_payload = {
            "bot_principal_id": bot_id,
            "parent_principal_id": owner_id,
            "name": bot_name,
            "display_name": f"Trending Bot {i}",
            "description": "Test trending",
            "system_instructions": "Test",
            "category": "general",
            "avatar_url": "https://example.com/a.jpg"
        }
        create_resp = client.post("/api/v1/influencers/create", json=create_payload, headers=headers)
        assert create_resp.status_code == 200
        
        # Create a conversation for each bot (returns 201)
        conv_resp = client.post("/api/v1/chat/conversations", json={"influencer_id": bot_id}, headers=headers)
        assert conv_resp.status_code == 201
        conv_id = conv_resp.json()["id"]
        bots.append({"id": bot_id, "conv_id": conv_id, "headers": headers})

    # 2. Send 2 messages to Bot 1 (index 0) and 3 messages to Bot 2 (index 1)
    # Total messages for Bot 1: 1 (greeting) + 2 (user) + 2 (assistant) = 5
    # Total messages for Bot 2: 1 (greeting) + 3 (user) + 3 (assistant) = 7
    
    # Bot 1 - 2 messages
    for _ in range(2):
        resp = client.post(f"/api/v1/chat/conversations/{bots[0]['conv_id']}/messages",
                           json={"conversation_id": bots[0]["conv_id"], "content": "hi", "message_type": "text"},
                           headers=bots[0]["headers"])
        assert resp.status_code == 200
        
    # Bot 2 - 3 messages
    for _ in range(3):
        resp = client.post(f"/api/v1/chat/conversations/{bots[1]['conv_id']}/messages",
                           json={"conversation_id": bots[1]["conv_id"], "content": "hi", "message_type": "text"},
                           headers=bots[1]["headers"])
        assert resp.status_code == 200

    # 3. Get trending list
    resp = client.get("/api/v1/influencers/trending")
    assert resp.status_code == 200
    data = resp.json()
    
    influencers = data["influencers"]
    # Find our bots in the list
    bot1_data = next((b for b in influencers if b["id"] == bots[0]["id"]), None)
    bot2_data = next((b for b in influencers if b["id"] == bots[1]["id"]), None)
    
    assert bot1_data is not None
    assert bot2_data is not None
    
    # Verify counts (strictly user messages received by bot)
    assert bot1_data["message_count"] == 2
    assert bot2_data["message_count"] == 3
    
    # Check ordering relative to each other (Bot 2 with 7 should be above Bot 1 with 5)
    idx1 = next(i for i, b in enumerate(influencers) if b["id"] == bots[0]["id"])
    idx2 = next(i for i, b in enumerate(influencers) if b["id"] == bots[1]["id"])
    assert idx2 < idx1
