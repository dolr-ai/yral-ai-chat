import time

import httpx
import pytest


@pytest.mark.asyncio
async def test_image_generation_real_ahaan(client, auth_headers):
    """
    Real-world test case for image generation with Ahaan Sharma.
    This test makes actual calls to Replicate and Storj.
    """
    # 1. Find Ahaan Sharma's influencer ID
    influencers_resp = client.get("/api/v1/influencers?limit=50")
    assert influencers_resp.status_code == 200
    ahaan = next((i for i in influencers_resp.json()["influencers"] if "Ahaan Sharma" in i["display_name"]), None)
    assert ahaan is not None, "Ahaan Sharma not found in influencer list"
    influencer_id = ahaan["id"]
    
    # 2. Create a conversation
    conv_resp = client.post(
        "/api/v1/chat/conversations",
        json={"influencer_id": influencer_id},
        headers=auth_headers
    )
    assert conv_resp.status_code == 201
    conversation_id = conv_resp.json()["id"]
    
    # 3. Request Image Generation
    prompt = "Ahan Sharma working out in a futuristic gym, wearing fitness gear, highly detailed bodybuilding pose"
    gen_resp = client.post(
        f"/api/v1/chat/conversations/{conversation_id}/images",
        json={"prompt": prompt},
        headers=auth_headers
    )
    
    # This might take some time, but since our implementation is async and Replicate is fast,
    # we expect it to complete within the request timeout or fail.
    # The default timeout for TestClient might be short, but we've seen it takes ~5-10s.
    assert gen_resp.status_code == 201, f"Generation failed: {gen_resp.text}"
    data = gen_resp.json()
    
    # 4. Verify Message Structure
    assert data["message_type"] == "image"
    assert len(data["media_urls"]) == 1
    media_url = data["media_urls"][0]
    assert "storj" in media_url.lower() or "your-objectstorage.com" in media_url.lower() or "s3" in media_url.lower()
    
    # 5. Verify image is retrievable via chat history
    time.sleep(1) # Small delay for DB consistency
    history_resp = client.get(f"/api/v1/chat/conversations/{conversation_id}/messages", headers=auth_headers)
    assert history_resp.status_code == 200
    history_data = history_resp.json()
    
    # Found the image message in history - sort by created_at to get latest
    messages = history_data["messages"]
    image_msg = next((m for m in sorted(messages, key=lambda x: x["created_at"], reverse=True)
                      if m["message_type"] == "image"), None)
    assert image_msg is not None
    assert len(image_msg["media_urls"]) == 1
    
    # Compare only the base URL (excluding query parameters which have dynamic signatures)
    history_url_base = image_msg["media_urls"][0].split("?")[0]
    gen_url_base = media_url.split("?")[0]
    assert history_url_base == gen_url_base
    
    # 6. Verify URL is accessible
    async with httpx.AsyncClient() as hclient:
        media_get = await hclient.get(media_url)
        assert media_get.status_code == 200
        assert "image/" in media_get.headers.get("Content-Type", "")
