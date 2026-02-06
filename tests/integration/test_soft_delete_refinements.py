from uuid import UUID

import pytest


@pytest.mark.asyncio
async def test_discontinued_bot_hidden_from_list(client, auth_headers):
    """Test that a discontinued bot is hidden from the v1 list"""
    # 1. Create a bot
    bot_id = f"test-hide-{UUID(int=1)}"
    create_payload = {
        "bot_principal_id": bot_id,
        "parent_principal_id": "test_user_default",
        "name": f"hide_bot_{UUID(int=1)}",
        "display_name": "Hide Bot",
        "description": "Test hiding",
        "system_instructions": "Test",
        "category": "general"
    }
    client.post("/api/v1/influencers/create", json=create_payload, headers=auth_headers)
    
    # 2. Verify it shows in list
    resp = client.get("/api/v1/influencers")
    assert any(b["id"] == bot_id for b in resp.json()["influencers"])
    
    # 3. Soft delete it
    client.delete(f"/api/v1/influencers/{bot_id}", headers=auth_headers)
    
    # 4. Verify it's hidden from list
    resp = client.get("/api/v1/influencers")
    assert not any(b["id"] == bot_id for b in resp.json()["influencers"])

@pytest.mark.asyncio
async def test_block_message_to_discontinued_bot(client, auth_headers):
    """Test that new messages to a discontinued bot are blocked"""
    # 1. Create bot and conversation
    bot_id = f"test-block-{UUID(int=1)}"
    create_payload = {
        "bot_principal_id": bot_id,
        "parent_principal_id": "test_user_default",
        "name": f"block_bot_{UUID(int=1)}",
        "display_name": "Block Bot",
        "description": "Test blocking",
        "system_instructions": "Test",
        "category": "general"
    }
    client.post("/api/v1/influencers/create", json=create_payload, headers=auth_headers)
    
    conv_resp = client.post("/api/v1/chat/conversations", json={"influencer_id": bot_id}, headers=auth_headers)
    conv_id = conv_resp.json()["id"]
    
    # 2. Soft delete the bot
    client.delete(f"/api/v1/influencers/{bot_id}", headers=auth_headers)
    
    # 3. Try to send a message
    msg_payload = {
        "conversation_id": conv_id,
        "content": "Hello",
        "message_type": "text"
    }
    resp = client.post(f"/api/v1/chat/conversations/{conv_id}/messages", json=msg_payload, headers=auth_headers)
    
    # 4. Verify forbidden
    assert resp.status_code == 403
    assert "deleted" in resp.json()["message"].lower()

@pytest.mark.asyncio
async def test_block_image_generation_for_discontinued_bot(client, auth_headers):
    """Test that image generation for a discontinued bot is blocked"""
    # 1. Create bot and conversation
    bot_id = f"test-img-{UUID(int=1)}"
    create_payload = {
        "bot_principal_id": bot_id,
        "parent_principal_id": "test_user_default",
        "name": f"img_bot_{UUID(int=1)}",
        "display_name": "Img Bot",
        "description": "Test img blocking",
        "system_instructions": "Test",
        "category": "general"
    }
    client.post("/api/v1/influencers/create", json=create_payload, headers=auth_headers)
    
    conv_resp = client.post("/api/v1/chat/conversations", json={"influencer_id": bot_id}, headers=auth_headers)
    conv_id = conv_resp.json()["id"]
    
    # 2. Soft delete the bot
    client.delete(f"/api/v1/influencers/{bot_id}", headers=auth_headers)
    
    # 3. Try to generate an image
    resp = client.post(f"/api/v1/chat/conversations/{conv_id}/images", json={"prompt": "test"}, headers=auth_headers)
    
    # 4. Verify forbidden
    assert resp.status_code == 403
    assert "deleted" in resp.json()["message"].lower()
