"""
Repository for AI Influencer operations
"""
import json

from src.db.base import db
from src.models.entities import AIInfluencer


class InfluencerRepository:
    """Repository for AI influencer database operations"""

    async def list_all(self, limit: int = 50, offset: int = 0) -> list[AIInfluencer]:
        """List all influencers (both active and inactive)"""
        query = """
            SELECT 
                id, name, display_name, avatar_url, description, 
                category, system_instructions, personality_traits,
                initial_greeting, suggested_messages,
                is_active, created_at, updated_at, metadata
            FROM ai_influencers
            ORDER BY is_active DESC, created_at DESC
            LIMIT $1 OFFSET $2
        """

        rows = await db.fetch(query, limit, offset)
        return [self._row_to_influencer(row) for row in rows]

    async def get_by_id(self, influencer_id: str) -> AIInfluencer | None:
        """Get influencer by ID"""
        query = """
            SELECT 
                id, name, display_name, avatar_url, description, 
                category, system_instructions, personality_traits,
                initial_greeting, suggested_messages,
                is_active, created_at, updated_at, metadata
            FROM ai_influencers
            WHERE id = $1 AND is_active = true
        """

        row = await db.fetchone(query, influencer_id)
        return self._row_to_influencer(row) if row else None

    async def get_by_name(self, name: str) -> AIInfluencer | None:
        """Get influencer by name"""
        query = """
            SELECT 
                id, name, display_name, avatar_url, description, 
                category, system_instructions, personality_traits,
                initial_greeting, suggested_messages,
                is_active, created_at, updated_at, metadata
            FROM ai_influencers
            WHERE name = $1 AND is_active = true
        """

        row = await db.fetchone(query, name)
        return self._row_to_influencer(row) if row else None

    async def count_all(self) -> int:
        """Count all influencers (both active and inactive)"""
        query = "SELECT COUNT(*) FROM ai_influencers"
        return await db.fetchval(query)

    async def get_with_conversation_count(self, influencer_id: str) -> AIInfluencer | None:
        """Get influencer with conversation count"""
        query = """
            SELECT 
                i.id, i.name, i.display_name, i.avatar_url, i.description, 
                i.category, i.system_instructions, i.personality_traits,
                i.initial_greeting, i.suggested_messages,
                i.is_active, i.created_at, i.updated_at, i.metadata,
                COUNT(c.id) as conversation_count
            FROM ai_influencers i
            LEFT JOIN conversations c ON i.id = c.influencer_id
            WHERE i.id = $1 AND i.is_active = true
            GROUP BY i.id
        """

        row = await db.fetchone(query, influencer_id)
        if not row:
            return None

        influencer = self._row_to_influencer(row)
        influencer.conversation_count = row["conversation_count"]
        return influencer

    def _row_to_influencer(self, row) -> AIInfluencer:
        """Convert database row to AIInfluencer model"""

        # Parse JSONB fields if they're strings
        personality_traits = row["personality_traits"]
        if isinstance(personality_traits, str):
            personality_traits = json.loads(personality_traits)

        suggested_messages = row.get("suggested_messages")
        if isinstance(suggested_messages, str):
            try:
                suggested_messages = json.loads(suggested_messages)
            except json.JSONDecodeError:
                suggested_messages = []
        elif not isinstance(suggested_messages, list):
            suggested_messages = []

        metadata = row["metadata"]
        if isinstance(metadata, str):
            metadata = json.loads(metadata)

        return AIInfluencer(
            id=row["id"],
            name=row["name"],
            display_name=row["display_name"],
            avatar_url=row["avatar_url"],
            description=row["description"],
            category=row["category"],
            system_instructions=row["system_instructions"],
            personality_traits=personality_traits,
            initial_greeting=row.get("initial_greeting"),
            suggested_messages=suggested_messages,
            is_active=row["is_active"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            metadata=metadata,
        )


