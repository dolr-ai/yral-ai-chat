"""
Repository for Conversation operations
"""
import json
import uuid
from datetime import datetime
from uuid import UUID

from src.db.base import db
from src.models.entities import AIInfluencer, Conversation, LastMessageInfo, MessageRole


class ConversationRepository:
    """Repository for conversation database operations"""

    async def create(self, user_id: str, influencer_id: UUID) -> Conversation:
        """Create a new conversation"""
        conversation_id = str(uuid.uuid4())

        query = """
            INSERT INTO conversations (id, user_id, influencer_id)
            VALUES ($1, $2, $3)
        """

        await db.execute(query, conversation_id, user_id, str(influencer_id))

        result = await self.get_by_id(UUID(conversation_id))
        if result is None:
            raise RuntimeError(f"Failed to create conversation {conversation_id}")
        return result

    async def get_by_id(self, conversation_id: UUID) -> Conversation | None:
        """Get conversation by ID"""
        query = """
            SELECT
                c.id, c.user_id, c.influencer_id, c.created_at, c.updated_at, c.metadata,
                i.id as inf_id, i.name, i.display_name, i.avatar_url,
                i.suggested_messages
            FROM conversations c
            JOIN ai_influencers i ON c.influencer_id = i.id
            WHERE c.id = $1
        """

        row = await db.fetchone(query, str(conversation_id))
        return self._row_to_conversation_with_influencer(row) if row else None

    async def get_existing(self, user_id: str, influencer_id: UUID) -> Conversation | None:
        """Check if conversation already exists between user and influencer"""
        query = """
            SELECT
                c.id, c.user_id, c.influencer_id, c.created_at, c.updated_at, c.metadata,
                i.id as inf_id, i.name, i.display_name, i.avatar_url,
                i.suggested_messages
            FROM conversations c
            JOIN ai_influencers i ON c.influencer_id = i.id
            WHERE c.user_id = $1 AND c.influencer_id = $2
        """

        row = await db.fetchone(query, user_id, str(influencer_id))
        return self._row_to_conversation_with_influencer(row) if row else None

    async def list_by_user(
        self,
        user_id: str,
        influencer_id: UUID | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[Conversation]:
        """List conversations for a user"""
        if influencer_id:
            query = """
                SELECT
                    c.id, c.user_id, c.influencer_id, c.created_at, c.updated_at, c.metadata,
                    i.id as inf_id, i.name, i.display_name, i.avatar_url,
                    i.suggested_messages,
                    COUNT(m.id) as message_count
                FROM conversations c
                JOIN ai_influencers i ON c.influencer_id = i.id
                LEFT JOIN messages m ON c.id = m.conversation_id
                WHERE c.user_id = $1 AND c.influencer_id = $2
                GROUP BY c.id, i.id
                ORDER BY c.updated_at DESC
                LIMIT $3 OFFSET $4
            """
            rows = await db.fetch(query, user_id, str(influencer_id), limit, offset)
        else:
            query = """
                SELECT
                    c.id, c.user_id, c.influencer_id, c.created_at, c.updated_at, c.metadata,
                    i.id as inf_id, i.name, i.display_name, i.avatar_url,
                    i.suggested_messages,
                    COUNT(m.id) as message_count
                FROM conversations c
                JOIN ai_influencers i ON c.influencer_id = i.id
                LEFT JOIN messages m ON c.id = m.conversation_id
                WHERE c.user_id = $1
                GROUP BY c.id, i.id
                ORDER BY c.updated_at DESC
                LIMIT $2 OFFSET $3
            """
            rows = await db.fetch(query, user_id, limit, offset)

        conversations = []
        for row in rows:
            conv = self._row_to_conversation_with_influencer(row)
            message_count_val = row.get("message_count", 0)
            if isinstance(message_count_val, int):
                conv.message_count = message_count_val
            elif isinstance(message_count_val, str):
                try:
                    conv.message_count = int(message_count_val)
                except (ValueError, TypeError):
                    conv.message_count = 0
            else:
                conv.message_count = 0

            last_msg = await self._get_last_message(UUID(conv.id))
            conv.last_message = last_msg

            conversations.append(conv)

        return conversations

    async def count_by_user(self, user_id: str, influencer_id: UUID | None = None) -> int:
        """Count conversations for a user"""
        if influencer_id:
            query = "SELECT COUNT(*) FROM conversations WHERE user_id = $1 AND influencer_id = $2"
            result = await db.fetchval(query, user_id, str(influencer_id))
            return int(result) if result is not None and isinstance(result, int | str) else 0
        query = "SELECT COUNT(*) FROM conversations WHERE user_id = $1"
        result = await db.fetchval(query, user_id)
        return int(result) if result is not None and isinstance(result, int | str) else 0

    async def delete(self, conversation_id: UUID) -> int:
        """Delete conversation and return count of deleted messages"""
        count_query = "SELECT COUNT(*) FROM messages WHERE conversation_id = $1"
        result = await db.fetchval(count_query, str(conversation_id))
        message_count = int(result) if result is not None else 0

        delete_query = "DELETE FROM conversations WHERE id = $1"
        await db.execute(delete_query, str(conversation_id))

        return message_count

    async def update_metadata(self, conversation_id: UUID, metadata: dict[str, object]) -> None:
        """Update conversation metadata"""
        metadata_json = json.dumps(metadata)
        query = "UPDATE conversations SET metadata = $1 WHERE id = $2"
        await db.execute(query, metadata_json, str(conversation_id))

    async def _get_last_message(self, conversation_id: UUID) -> LastMessageInfo | None:
        """Get last message in conversation"""
        query = """
            SELECT content, role, created_at
            FROM messages
            WHERE conversation_id = $1
            ORDER BY created_at DESC
            LIMIT 1
        """

        row = await db.fetchone(query, str(conversation_id))
        if row:
            content = row.get("content")
            role_str = row.get("role")
            created_at_val = row.get("created_at")
            
            role = MessageRole(role_str) if isinstance(role_str, str) else MessageRole.USER
            created_at = created_at_val if isinstance(created_at_val, datetime) else datetime.now()
            
            return LastMessageInfo(
                content=str(content) if content is not None else None,
                role=role,
                created_at=created_at,
            )
        return None

    def _row_to_conversation(self, row) -> Conversation:
        """Convert database row to Conversation model"""
        metadata = row["metadata"]
        if isinstance(metadata, str):
            metadata = json.loads(metadata)

        return Conversation(
            id=row["id"],
            user_id=row["user_id"],
            influencer_id=row["influencer_id"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            metadata=metadata,
        )

    def _row_to_conversation_with_influencer(self, row) -> Conversation:
        """Convert database row to Conversation with influencer info"""
        conversation = self._row_to_conversation(row)

        suggested_messages = row.get("suggested_messages")
        if isinstance(suggested_messages, str):
            try:
                suggested_messages = json.loads(suggested_messages)
            except json.JSONDecodeError:
                suggested_messages = []
        elif not isinstance(suggested_messages, list):
            suggested_messages = []

        conversation.influencer = AIInfluencer(
            id=row["inf_id"],
            name=row["name"],
            display_name=row["display_name"],
            avatar_url=row["avatar_url"],
            system_instructions="",  # Not needed in list view
            suggested_messages=suggested_messages,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

        return conversation


