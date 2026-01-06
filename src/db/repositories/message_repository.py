"""
Repository for Message operations
"""
import json
import uuid
from uuid import UUID

from src.db.base import db
from src.models.entities import Message, MessageRole, MessageType


class MessageRepository:
    """Repository for message database operations"""

    async def create(
        self,
        conversation_id: UUID,
        role: MessageRole,
        content: str | None,
        message_type: MessageType,
        media_urls: list[str] = None,
        audio_url: str | None = None,
        audio_duration_seconds: int | None = None,
        token_count: int | None = None
    ) -> Message:
        """Create a new message"""
        message_id = str(uuid.uuid4())
        media_urls_json = json.dumps(media_urls or [])

        query = """
            INSERT INTO messages (
                id, conversation_id, role, content, message_type,
                media_urls, audio_url, audio_duration_seconds, token_count
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
        """

        await db.execute(
            query,
            message_id,
            str(conversation_id),
            role.value,
            content,
            message_type.value,
            media_urls_json,
            audio_url,
            audio_duration_seconds,
            token_count
        )

        return await self.get_by_id(UUID(message_id))

    async def get_by_id(self, message_id: UUID) -> Message | None:
        """Get message by ID"""
        query = """
            SELECT
                id, conversation_id, role, content, message_type,
                media_urls, audio_url, audio_duration_seconds,
                token_count, created_at, metadata
            FROM messages
            WHERE id = $1
        """

        row = await db.fetchone(query, str(message_id))
        return self._row_to_message(row) if row else None

    async def list_by_conversation(
        self,
        conversation_id: UUID,
        limit: int = 50,
        offset: int = 0,
        order: str = "desc"
    ) -> list[Message]:
        """List messages in a conversation"""
        order_clause = "DESC" if order.lower() == "desc" else "ASC"

        query = (
            "SELECT "
            "id, conversation_id, role, content, message_type, "
            "media_urls, audio_url, audio_duration_seconds, "
            "token_count, created_at, metadata "
            "FROM messages "
            "WHERE conversation_id = $1 "
            "ORDER BY created_at " + order_clause + " "
            "LIMIT $2 OFFSET $3"
        )

        rows = await db.fetch(query, str(conversation_id), limit, offset)
        return [self._row_to_message(row) for row in rows]

    async def get_recent_for_context(
        self,
        conversation_id: UUID,
        limit: int = 10
    ) -> list[Message]:
        """Get recent messages for AI context (ordered oldest to newest)"""
        query = """
            SELECT
                id, conversation_id, role, content, message_type,
                media_urls, audio_url, audio_duration_seconds,
                token_count, created_at, metadata
            FROM messages
            WHERE conversation_id = $1
            ORDER BY created_at DESC
            LIMIT $2
        """

        rows = await db.fetch(query, str(conversation_id), limit)
        return [self._row_to_message(row) for row in reversed(rows)]

    async def count_by_conversation(self, conversation_id: UUID) -> int:
        """Count messages in a conversation"""
        query = "SELECT COUNT(*) FROM messages WHERE conversation_id = $1"
        return await db.fetchval(query, str(conversation_id))

    async def count_all(self) -> int:
        """Count all messages"""
        query = "SELECT COUNT(*) FROM messages"
        return await db.fetchval(query)

    def _row_to_message(self, row) -> Message:
        """Convert database row to Message model"""
        media_urls = row["media_urls"]
        if isinstance(media_urls, str):
            media_urls = json.loads(media_urls)
        elif not isinstance(media_urls, list):
            media_urls = []

        metadata = row["metadata"]
        if isinstance(metadata, str):
            metadata = json.loads(metadata)

        return Message(
            id=row["id"],
            conversation_id=row["conversation_id"],
            role=MessageRole(row["role"]),
            content=row["content"],
            message_type=MessageType(row["message_type"]),
            media_urls=media_urls,
            audio_url=row["audio_url"],
            audio_duration_seconds=row["audio_duration_seconds"],
            token_count=row["token_count"],
            created_at=row["created_at"],
            metadata=metadata
        )


