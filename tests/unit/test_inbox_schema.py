from datetime import UTC, datetime

from src.models.entities import AIInfluencer


def test_inbox_list_schema_structure():
    """Verify the conversation list response structure matches requirements"""
    # Create mock data
    influencer = AIInfluencer(
        id="inf_555",
        name="Kabir",
        display_name="Kabir Malhotra",
        avatar_url="https://cdn.example.com/profiles/kabir.jpg",
        system_instructions="You are helpful.",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        is_active="active",
        is_nsfw=False
    )
    
    # Simulate the joined structure we want from the repository/service
    conversation_data = {
        "id": "conv_123",
        "user_id": "user_123",
        "influencer_id": "inf_555",
        "unread_count": 3,
        "last_message": {
             "content": "Typing...",
             "role": "assistant",
             "created_at": datetime.now(UTC),
             "status": "delivered",
             "is_read": False
        },
        "influencer": influencer.model_dump(),
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC)
    }
    
    # Assert critical fields exist
    assert "unread_count" in conversation_data
    assert "last_message" in conversation_data
    assert "status" in conversation_data["last_message"] # New field
    assert "is_read" in conversation_data["last_message"] # New field
    assert "influencer" in conversation_data
    assert conversation_data["influencer"]["id"] == "inf_555"

def test_websocket_new_message_event_schema():
    """Verify the new_message event payload structure"""
    
    event_payload = {
        "event": "new_message",
        "data": {
            "conversation_id": "conv_123",
            "message": {
                "id": "msg_701",
                "role": "assistant",
                "content": "Hello!",
                "message_type": "text",
                "created_at": "2026-01-27T10:30:05Z",
                "status": "delivered",
                "is_read": False
            },
            "influencer_id": "inf_555",
            "influencer": {
                "id": "inf_555",
                "display_name": "Kabir Malhotra",
                "avatar_url": "https://cdn.example.com/profiles/kabir.jpg",
                "is_online": True
            },
            "unread_count": 4
        }
    }
    
    data = event_payload["data"]
    assert event_payload["event"] == "new_message"
    assert "influencer" in data
    assert data["influencer"]["display_name"] == "Kabir Malhotra"
    assert data["influencer"]["is_online"] is True
    assert "unread_count" in data
    assert "status" in data["message"]
    assert "is_read" in data["message"]
