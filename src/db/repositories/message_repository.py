"""
Repository for Message operations
"""
from typing import List, Optional
from uuid import UUID
import uuid
from src.db.base import db
from src.models.entities import Message, MessageType, MessageRole


class MessageRepository:
    """Repository for message database operations"""
    
    async def create(
        self,
        conversation_id: UUID,
        role: MessageRole,
        content: Optional[str],
        message_type: MessageType,
        media_urls: List[str] = None,
        audio_url: Optional[str] = None,
        audio_duration_seconds: Optional[int] = None,
        token_count: Optional[int] = None
    ) -> Message:
        """Create a new message"""
        import json
        
        # Generate UUID for SQLite (no uuid-ossp extension)
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
        
        # Fetch the created message
        return await self.get_by_id(UUID(message_id))
    
    async def get_by_id(self, message_id: UUID) -> Optional[Message]:
        """Get message by ID"""
        query = """
            SELECT 
                id, conversation_id, role, content, message_type,
                media_urls, audio_url, audio_duration_seconds,
                token_count, created_at, metadata
            FROM messages
            WHERE id = $1
        """
        
        row = await db.fetchone(query, message_id)
        return self._row_to_message(row) if row else None
    
    async def list_by_conversation(
        self,
        conversation_id: UUID,
        limit: int = 50,
        offset: int = 0,
        order: str = "desc"
    ) -> List[Message]:
        """List messages in a conversation"""
        order_clause = "DESC" if order.lower() == "desc" else "ASC"
        
        query = f"""
            SELECT 
                id, conversation_id, role, content, message_type,
                media_urls, audio_url, audio_duration_seconds,
                token_count, created_at, metadata
            FROM messages
            WHERE conversation_id = $1
            ORDER BY created_at {order_clause}
            LIMIT $2 OFFSET $3
        """
        
        rows = await db.fetch(query, conversation_id, limit, offset)
        return [self._row_to_message(row) for row in rows]
    
    async def get_recent_for_context(
        self,
        conversation_id: UUID,
        limit: int = 10
    ) -> List[Message]:
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
        
        rows = await db.fetch(query, conversation_id, limit)
        # Reverse to get oldest to newest for AI context
        return [self._row_to_message(row) for row in reversed(rows)]
    
    async def count_by_conversation(self, conversation_id: UUID) -> int:
        """Count messages in a conversation"""
        query = "SELECT COUNT(*) FROM messages WHERE conversation_id = $1"
        return await db.fetchval(query, conversation_id)
    
    async def count_all(self) -> int:
        """Count all messages"""
        query = "SELECT COUNT(*) FROM messages"
        return await db.fetchval(query)
    
    def _row_to_message(self, row) -> Message:
        """Convert database row to Message model"""
        import json
        
        # Parse JSONB fields if they're strings
        media_urls = row['media_urls']
        if isinstance(media_urls, str):
            media_urls = json.loads(media_urls)
        elif not isinstance(media_urls, list):
            media_urls = []
        
        metadata = row['metadata']
        if isinstance(metadata, str):
            metadata = json.loads(metadata)
        
        return Message(
            id=row['id'],
            conversation_id=row['conversation_id'],
            role=MessageRole(row['role']),
            content=row['content'],
            message_type=MessageType(row['message_type']),
            media_urls=media_urls,
            audio_url=row['audio_url'],
            audio_duration_seconds=row['audio_duration_seconds'],
            token_count=row['token_count'],
            created_at=row['created_at'],
            metadata=metadata
        )


