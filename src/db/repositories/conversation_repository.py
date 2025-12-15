"""
Repository for Conversation operations
"""
from typing import Any
from uuid import UUID
import uuid
from src.db.base import db
from src.models.entities import Conversation, AIInfluencer


class ConversationRepository:
    """Repository for conversation database operations"""
    
    async def create(self, user_id: str, influencer_id: UUID) -> Conversation:
        """Create a new conversation"""
        # Generate UUID for SQLite (no uuid-ossp extension)
        conversation_id = str(uuid.uuid4())
        
        query = """
            INSERT INTO conversations (id, user_id, influencer_id)
            VALUES ($1, $2, $3)
        """
        
        await db.execute(query, conversation_id, user_id, str(influencer_id))
        
        # Fetch the created conversation
        return await self.get_by_id(UUID(conversation_id))
    
    async def get_by_id(self, conversation_id: UUID) -> Conversation | None:
        """Get conversation by ID"""
        query = """
            SELECT 
                c.id, c.user_id, c.influencer_id, c.created_at, c.updated_at, c.metadata,
                i.id as inf_id, i.name, i.display_name, i.avatar_url
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
                i.id as inf_id, i.name, i.display_name, i.avatar_url
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
        offset: int = 0
    ) -> list[Conversation]:
        """List conversations for a user"""
        if influencer_id:
            query = """
                SELECT 
                    c.id, c.user_id, c.influencer_id, c.created_at, c.updated_at, c.metadata,
                    i.id as inf_id, i.name, i.display_name, i.avatar_url,
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
            conv.message_count = row['message_count']
            
            # Get last message
            last_msg = await self._get_last_message(conv.id)
            conv.last_message = last_msg
            
            conversations.append(conv)
        
        return conversations
    
    async def count_by_user(self, user_id: str, influencer_id: UUID | None = None) -> int:
        """Count conversations for a user"""
        if influencer_id:
            query = "SELECT COUNT(*) FROM conversations WHERE user_id = $1 AND influencer_id = $2"
            return await db.fetchval(query, user_id, str(influencer_id))
        else:
            query = "SELECT COUNT(*) FROM conversations WHERE user_id = $1"
            return await db.fetchval(query, user_id)
    
    async def delete(self, conversation_id: UUID) -> int:
        """Delete conversation and return count of deleted messages"""
        # Count messages first
        count_query = "SELECT COUNT(*) FROM messages WHERE conversation_id = $1"
        message_count = await db.fetchval(count_query, str(conversation_id))
        
        # Delete conversation (messages will cascade)
        delete_query = "DELETE FROM conversations WHERE id = $1"
        await db.execute(delete_query, str(conversation_id))
        
        return message_count
    
    async def _get_last_message(self, conversation_id: UUID) -> dict[str, Any] | None:
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
            return {
                "content": row['content'],
                "role": row['role'],
                "created_at": row['created_at']
            }
        return None
    
    def _row_to_conversation(self, row) -> Conversation:
        """Convert database row to Conversation model"""
        import json
        
        # Parse JSONB fields if they're strings
        metadata = row['metadata']
        if isinstance(metadata, str):
            metadata = json.loads(metadata)
        
        return Conversation(
            id=row['id'],
            user_id=row['user_id'],
            influencer_id=row['influencer_id'],
            created_at=row['created_at'],
            updated_at=row['updated_at'],
            metadata=metadata
        )
    
    def _row_to_conversation_with_influencer(self, row) -> Conversation:
        """Convert database row to Conversation with influencer info"""
        conversation = self._row_to_conversation(row)
        
        # Add influencer basic info
        conversation.influencer = AIInfluencer(
            id=row['inf_id'],
            name=row['name'],
            display_name=row['display_name'],
            avatar_url=row['avatar_url'],
            system_instructions="",  # Not needed in list view
            created_at=row['created_at'],
            updated_at=row['updated_at']
        )
        
        return conversation


