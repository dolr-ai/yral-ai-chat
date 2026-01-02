"""
Test for numeric content duplication bug (70 -> 7070, 56 -> 5656)

This test verifies that when sending numeric values like "70", 
Gemini does not interpret them as duplicated values like "7070".
"""
import re

# Ahaan Sharma's influencer ID (known to have initial_greeting)
AHAAN_INFLUENCER_ID = "qg2pi-g3xl4-uprdd-macwr-64q7r-plotv-xm3bg-iayu3-rnpux-7ikkz-hqe"


def test_numeric_content_duplication_bug(client, auth_headers):
    """
    Test that sending "70" after a conversation does not result in Gemini 
    interpreting it as "7070" or any other duplication.
    
    Flow:
    1. Create conversation with Ahaan
    2. Send "hi" -> wait for response
    3. Send "fat loss" -> wait for response  
    4. Send "70" -> analyze response for "7070" duplication
    """
    # Step 1: Create conversation with Ahaan
    create_response = client.post(
        "/api/v1/chat/conversations",
        json={"influencer_id": AHAAN_INFLUENCER_ID},
        headers=auth_headers
    )
    assert create_response.status_code == 201
    conversation_data = create_response.json()
    conversation_id = conversation_data["id"]
    
    try:
        # Step 2: Send "hi" and wait for response
        hi_response = client.post(
            f"/api/v1/chat/conversations/{conversation_id}/messages",
            json={
                "content": "hi",
                "message_type": "text"
            },
            headers=auth_headers
        )
        assert hi_response.status_code == 200
        hi_data = hi_response.json()
        
        # Verify "hi" message was saved correctly
        assert hi_data["user_message"]["content"] == "hi"
        assert hi_data["assistant_message"]["content"]
        hi_assistant_response = hi_data["assistant_message"]["content"]
        print("\n📝 CONVERSATION MESSAGE 1")
        print("👤 User: 'hi'")
        print(f"🤖 Bot: {hi_assistant_response[:100]}...")
        
        # Step 3: Send "fat loss" and wait for response
        fat_loss_response = client.post(
            f"/api/v1/chat/conversations/{conversation_id}/messages",
            json={
                "content": "fat loss",
                "message_type": "text"
            },
            headers=auth_headers
        )
        assert fat_loss_response.status_code == 200
        fat_loss_data = fat_loss_response.json()
        
        # Verify "fat loss" message was saved correctly
        assert fat_loss_data["user_message"]["content"] == "fat loss"
        assert fat_loss_data["assistant_message"]["content"]
        fat_loss_assistant_response = fat_loss_data["assistant_message"]["content"]
        print("\n📝 CONVERSATION MESSAGE 2")
        print("👤 User: 'fat loss'")
        print(f"🤖 Bot: {fat_loss_assistant_response[:100]}...")
        
        # Step 4: Send "70" and analyze response for duplication
        numeric_response = client.post(
            f"/api/v1/chat/conversations/{conversation_id}/messages",
            json={
                "content": 70,  # Send as integer to test type conversion
                "message_type": "text"
            },
            headers=auth_headers
        )
        assert numeric_response.status_code == 200
        numeric_data = numeric_response.json()
        
        # Verify "70" message was saved correctly (should be converted to string "70")
        user_msg = numeric_data["user_message"]
        assert user_msg["content"] == "70", \
            f"User message content should be '70' but got '{user_msg['content']}'"
        
        assistant_msg = numeric_data["assistant_message"]
        assistant_content = assistant_msg["content"]
        
        print("\n📝 CONVERSATION MESSAGE 3")
        print("📤 Sent numeric value: 70 (as JSON number, not string)")
        print(f"💾 User message saved as: '{user_msg['content']}'")
        print(f"👤 User: '{user_msg['content']}'")
        print(f"🤖 Bot (full message):\n   {assistant_content}")
        print(f"📊 Bot response length: {len(assistant_content)} characters")
        
        # Analyze response for duplication patterns
        # Check for "7070" (exact duplication)
        has_7070 = "7070" in assistant_content
        # Check for "70 70" (with space)
        has_70_space_70 = bool(re.search(r"70\s+70", assistant_content))
        # Check for "70kg" or "70 kg" (normal usage - should be OK)
        has_70_kg = bool(re.search(r"70\s*kg", assistant_content, re.IGNORECASE))
        
        # Check if the response mentions "70" in a way that suggests duplication
        # Look for patterns like "7070 kg", "70 70", etc.
        suspicious_patterns = [
            r"7070",  # Exact duplication
            r"70\s+70",  # Space-separated duplication
            r"70\s*70",  # Any whitespace between
            r"seventy\s+seventy",  # Word form duplication
        ]
        
        found_suspicious = False
        for pattern in suspicious_patterns:
            if re.search(pattern, assistant_content, re.IGNORECASE):
                found_suspicious = True
                print(f"\n⚠️  WARNING: Found suspicious pattern '{pattern}' in response!")
                break
        
        # The main assertion: "7070" should NOT appear in the response
        # (unless it's a legitimate part of a larger number like "17070" or context)
        # We check for standalone "7070" or "70 70" patterns
        assert not has_7070, \
            f"❌ BUG DETECTED: Response contains '7070' which indicates duplication!\n" \
            f"   Full response: {assistant_content}"
        
        assert not has_70_space_70, \
            f"❌ BUG DETECTED: Response contains '70 70' (space-separated) which indicates duplication!\n" \
            f"   Full response: {assistant_content}"
        
        # Log success
        print("\n✅ No duplication detected in bot response")
        print(f"   Bot correctly received: '{user_msg['content']}'")
        print(f"   Bot response (full): {assistant_content}")
        
        # Additional verification: Check that the message was stored correctly in DB
        messages_response = client.get(
            f"/api/v1/chat/conversations/{conversation_id}/messages",
            params={"limit": 10, "order": "desc"},
            headers=auth_headers
        )
        assert messages_response.status_code == 200
        messages_data = messages_response.json()
        
        # Find the "70" message in the history
        found_70_message = None
        for msg in messages_data["messages"]:
            if msg["id"] == user_msg["id"]:
                found_70_message = msg
                break
        
        assert found_70_message is not None, "Message '70' not found in conversation history"
        assert found_70_message["content"] == "70", \
            f"Message stored in DB as '{found_70_message['content']}' but should be '70'"
        
        print(f"✅ Message correctly stored in database as: '{found_70_message['content']}'")
        
    finally:
        # Cleanup: Delete the conversation
        try:
            client.delete(
                f"/api/v1/chat/conversations/{conversation_id}",
                headers=auth_headers
            )
        except Exception:
            pass  # Ignore cleanup errors


def test_numeric_content_duplication_with_string(client, auth_headers):
    """
    Same test as above but sending "70" as a string instead of integer.
    This tests the string path through the validation.
    """
    # Create conversation with Ahaan
    create_response = client.post(
        "/api/v1/chat/conversations",
        json={"influencer_id": AHAAN_INFLUENCER_ID},
        headers=auth_headers
    )
    assert create_response.status_code == 201
    conversation_id = create_response.json()["id"]
    
    try:
        # Send "hi"
        client.post(
            f"/api/v1/chat/conversations/{conversation_id}/messages",
            json={"content": "hi", "message_type": "text"},
            headers=auth_headers
        )
        
        # Send "fat loss"
        client.post(
            f"/api/v1/chat/conversations/{conversation_id}/messages",
            json={"content": "fat loss", "message_type": "text"},
            headers=auth_headers
        )
        
        # Send "70" as STRING
        response = client.post(
            f"/api/v1/chat/conversations/{conversation_id}/messages",
            json={
                "content": "70",  # Send as string
                "message_type": "text"
            },
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify content
        assert data["user_message"]["content"] == "70"
        assistant_content = data["assistant_message"]["content"]
        
        # Check for duplication
        assert "7070" not in assistant_content, \
            f"❌ BUG: Response contains '7070': {assistant_content}"
        assert not re.search(r"70\s+70", assistant_content), \
            f"❌ BUG: Response contains '70 70': {assistant_content}"
        
    finally:
        # Cleanup
        try:
            client.delete(
                f"/api/v1/chat/conversations/{conversation_id}",
                headers=auth_headers
            )
        except Exception:
            pass

