"""
Test for numeric content duplication bug (e.g., "70" -> "7070")
Tests with real API calls to Ahaan influencer
"""
import pytest
import json


@pytest.fixture(scope="function")
def ahaan_conversation_id(client, auth_headers):
    """
    Create a fresh conversation with Ahaan for each test
    """
    # Ahaan Sharma's influencer ID
    ahaan_id = "qg2pi-g3xl4-uprdd-macwr-64q7r-plotv-xm3bg-iayu3-rnpux-7ikkz-hqe"
    
    # Create conversation
    response = client.post(
        "/api/v1/chat/conversations",
        json={"influencer_id": ahaan_id},
        headers=auth_headers
    )
    assert response.status_code == 201
    conversation_id = response.json()["id"]
    
    yield conversation_id
    
    # Cleanup: Delete the conversation
    try:
        client.delete(f"/api/v1/chat/conversations/{conversation_id}", headers=auth_headers)
    except Exception:
        pass  # Ignore cleanup errors


def test_numeric_content_duplication_bug(client, ahaan_conversation_id, auth_headers):
    """
    Test the numeric content duplication bug:
    1. Send a message about weight loss
    2. Send just a number like "70" (as JSON number, not string)
    3. Check if bot response contains "7070" (duplication bug)
    
    This test makes real API calls to detect the duplication issue.
    """
    # Step 1: Send first message about weight loss
    response1 = client.post(
        f"/api/v1/chat/conversations/{ahaan_conversation_id}/messages",
        json={
            "content": "I want to lose weight",
            "message_type": "text"
        },
        headers=auth_headers
    )
    
    assert response1.status_code == 200, f"First message failed: {response1.text}"
    data1 = response1.json()
    
    # Verify first message was sent correctly
    assert "user_message" in data1
    assert "assistant_message" in data1
    assert data1["user_message"]["content"] == "I want to lose weight"
    
    print(f"\n{'='*80}")
    print(f"📝 CONVERSATION MESSAGE 1")
    print(f"{'='*80}")
    print(f"👤 User: '{data1['user_message']['content']}'")
    first_bot_response = data1['assistant_message']['content']
    print(f"🤖 Bot (full message):")
    print(f"   {first_bot_response}")
    print(f"📊 Bot response length: {len(first_bot_response)} characters")
    print(f"\n📋 Complete API Response (JSON):")
    print(json.dumps(data1, indent=2, ensure_ascii=False))
    print(f"{'='*80}")
    
    # Step 2: Send just a number "70" - send it as a JSON number (not string) to trigger the bug
    # This simulates what happens when frontend sends numeric values
    # Send as JSON number (70, not "70") to trigger the bug
    payload = {
        "content": 70,  # Send as number, not string!
        "message_type": "text"
    }
    
    # Use client.post() - both TestClient and RemoteClient support this
    # The json parameter will serialize 70 as a JSON number, which is what we want to test
    response2 = client.post(
        f"/api/v1/chat/conversations/{ahaan_conversation_id}/messages",
        json=payload,  # This will send 70 as JSON number, not string "70"
        headers=auth_headers,
    )
    assert response2.status_code == 200, f"Second message failed: {response2.text}"
    data2 = response2.json()
    
    # Verify user message was saved correctly
    user_msg = data2["user_message"]
    user_content = user_msg["content"]
    
    print(f"\n{'='*80}")
    print(f"📝 CONVERSATION MESSAGE 2")
    print(f"{'='*80}")
    print(f"📤 Sent numeric value: 70 (as JSON number, not string)")
    print(f"💾 User message saved as: '{user_content}'")
    assistant_response = data2['assistant_message']['content']
    print(f"👤 User: '{user_content}'")
    print(f"🤖 Bot (full message):")
    print(f"   {assistant_response}")
    print(f"📊 Bot response length: {len(assistant_response)} characters")
    print(f"\n📋 Complete API Response (JSON):")
    print(json.dumps(data2, indent=2, ensure_ascii=False))
    print(f"{'='*80}")
    
    # Step 3: Check if bot response contains "7070" (the duplication bug)
    assistant_content = data2["assistant_message"]["content"]
    
    # Check for duplication
    has_duplication = "7070" in assistant_content
    
    if has_duplication:
        print(f"\n❌ BUG DETECTED: Bot response contains '7070' (duplication detected!)")
        print(f"   Full bot response:")
        print(f"   {assistant_content}")
        pytest.fail(
            f"Content duplication bug detected! "
            f"Sent '70' but bot received '7070'. "
            f"Bot response (full): {assistant_content}"
        )
    else:
        print(f"\n✅ No duplication detected in bot response")
        print(f"   Bot correctly received: '{user_content}'")
        print(f"   Bot response (full): {assistant_content}")
    
    # Additional verification: Check that user message was saved correctly
    # It should be "70" not "7070"
    assert user_content == "70", \
        f"User message content was modified! Expected '70' but got '{user_content}'"
    
    # Verify the message doesn't contain duplication
    assert "7070" not in user_content, \
        f"User message content was duplicated! Got '{user_content}' instead of '70'"
    
    # Verify assistant didn't receive duplicated content
    assert "7070" not in assistant_content, \
        f"Assistant received duplicated content! Response contains '7070': {assistant_content}"

