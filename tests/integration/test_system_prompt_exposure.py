from uuid import UUID

import pytest

from src.core.moderation import MODERATION_PROMPT, STYLE_PROMPT


@pytest.mark.asyncio
async def test_system_prompt_exposure_and_stripping(client, auth_headers):
    """Test that system_prompt is exposed and stripped of guardrails"""
    # 1. Create a bot with a specific prompt
    bot_id = f"test-prompt-{UUID(int=100)}"
    user_prompt = "You are a helpful assistant for testing prompt exposure."
    create_payload = {
        "bot_principal_id": bot_id,
        "parent_principal_id": "test_user_default",
        "name": f"pb{UUID(int=100).hex[:8]}",
        "display_name": "Prompt Bot",
        "description": "Test prompt exposure",
        "system_instructions": user_prompt,
        "category": "general"
    }
    client.post("/api/v1/influencers/create", json=create_payload, headers=auth_headers)
    
    # 2. Get influencer details
    resp = client.get(f"/api/v1/influencers/{bot_id}")
    assert resp.status_code == 200
    data = resp.json()
    
    # 3. Verify system_prompt exists and is stripped
    assert "system_prompt" in data
    assert data["system_prompt"] == user_prompt
    
    # 4. Verify original instructions still have guardrails (internally)
    # We can't see the internal system_instructions via public API easily if we only expose system_prompt
    # but we can verify that system_prompt does NOT contain the guardrails
    assert STYLE_PROMPT not in data["system_prompt"]
    assert MODERATION_PROMPT not in data["system_prompt"]

@pytest.mark.asyncio
async def test_update_system_prompt_exposure(client, auth_headers):
    """Test that system_prompt is correctly updated and exposed"""
    # 1. Create bot
    bot_id = f"test-update-prompt-{UUID(int=101)}"
    create_payload = {
        "bot_principal_id": bot_id,
        "parent_principal_id": "test_user_default",
        "name": f"ub{UUID(int=101).hex[:8]}",
        "display_name": "Update Bot",
        "description": "Test update prompt exposure",
        "system_instructions": "Initial prompt",
        "category": "general"
    }
    client.post("/api/v1/influencers/create", json=create_payload, headers=auth_headers)
    
    # 2. Update system prompt
    new_prompt = "Updated user prompt"
    patch_resp = client.patch(
        f"/api/v1/influencers/{bot_id}/system-prompt",
        json={"system_instructions": new_prompt},
        headers=auth_headers
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["system_prompt"] == new_prompt
