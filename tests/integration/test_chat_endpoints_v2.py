"""
Tests for chat endpoints (V2 - Conversation Listing Only)
"""

from datetime import datetime
from uuid import UUID


def test_list_conversations(client, test_conversation_id, auth_headers):
    """Test listing user's conversations"""
    response = client.get("/api/v2/chat/conversations", headers=auth_headers)

    assert response.status_code == 200
    data = response.json()

    # Verify response structure (V2 is paginated object)
    assert "conversations" in data
    assert "total" in data
    assert isinstance(data["conversations"], list)
    assert len(data["conversations"]) > 0


def test_list_conversations_with_pagination(client, auth_headers):
    """Test listing conversations with custom pagination"""
    # Create a few more conversations to test pagination if needed,
    # but fixtures usually provide enough context.
    response = client.get("/api/v2/chat/conversations?limit=5&offset=0", headers=auth_headers)

    assert response.status_code == 200
    data = response.json()

    assert "conversations" in data
    assert len(data["conversations"]) <= 5


def test_list_conversations_filtered_by_influencer(client, test_influencer_id, auth_headers):
    """Test listing conversations filtered by influencer_id"""
    response = client.get(f"/api/v2/chat/conversations?influencer_id={test_influencer_id}", headers=auth_headers)

    assert response.status_code == 200
    data = response.json()
    assert "conversations" in data
    
    # All conversations should be with the specified influencer
    for conv in data["conversations"]:
        assert conv["influencer"]["id"] == test_influencer_id


def test_list_conversations_response_structure(client, test_conversation_id, auth_headers):
    """Test conversation response contains all required fields"""
    response = client.get("/api/v2/chat/conversations", headers=auth_headers)

    assert response.status_code == 200
    data = response.json()
    assert "conversations" in data
    assert len(data["conversations"]) > 0

    conv = data["conversations"][0]

    # Verify required fields
    assert "id" in conv
    assert "user_id" in conv
    assert "influencer_id" in conv
    assert "influencer" in conv
    assert "created_at" in conv
    assert "updated_at" in conv
    assert "unread_count" in conv
    assert "message_count" in conv
    
    # Check removed fields are NOT present
    assert "recent_messages" not in conv

    # Verify data types
    UUID(conv["id"])
    assert isinstance(conv["user_id"], str)
    assert isinstance(conv["influencer_id"], str)
    assert isinstance(conv["unread_count"], int)

    # Verify influencer structure
    influencer = conv["influencer"]
    assert "id" in influencer
    assert "name" in influencer
    assert "display_name" in influencer
    assert "avatar_url" in influencer
    assert "is_online" in influencer
    assert isinstance(influencer["is_online"], bool)

    # Verify timestamps
    datetime.fromisoformat(conv["created_at"])
    datetime.fromisoformat(conv["updated_at"])
