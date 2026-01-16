"""
Repository for AI Influencer operations
"""

import json

from src.db.base import db
from src.models.entities import AIInfluencer, InfluencerStatus


class InfluencerRepository:
    """Repository for AI influencer database operations"""

    async def list_all(self, limit: int = 50, offset: int = 0) -> list[AIInfluencer]:
        """List all influencers (both active and inactive)"""
        query = """
            SELECT
                id, name, display_name, avatar_url, description,
                category, system_instructions, personality_traits,
                initial_greeting, suggested_messages,
                is_active, is_nsfw, created_at, updated_at, metadata
            FROM ai_influencers
            ORDER BY CASE is_active
                WHEN 'active' THEN 1
                WHEN 'coming_soon' THEN 2
                WHEN 'discontinued' THEN 3
            END, created_at DESC
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
                is_active, is_nsfw, created_at, updated_at, metadata
            FROM ai_influencers
            WHERE id = $1 AND is_active = 'active'
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
                is_active, is_nsfw, created_at, updated_at, metadata
            FROM ai_influencers
            WHERE name = $1 AND is_active = 'active'
        """

        row = await db.fetchone(query, name)
        return self._row_to_influencer(row) if row else None

    async def count_all(self) -> int:
        """Count all influencers (both active and inactive)"""
        query = "SELECT COUNT(*) FROM ai_influencers"
        result = await db.fetchval(query)
        return int(result) if result is not None else 0

    async def get_with_conversation_count(self, influencer_id: str) -> AIInfluencer | None:
        """Get influencer with conversation count"""
        query = """
            SELECT
                i.id, i.name, i.display_name, i.avatar_url, i.description,
                i.category, i.system_instructions, i.personality_traits,
                i.initial_greeting, i.suggested_messages,
                i.is_active, i.is_nsfw, i.created_at, i.updated_at, i.metadata,
                COUNT(c.id) as conversation_count
            FROM ai_influencers i
            LEFT JOIN conversations c ON i.id = c.influencer_id
            WHERE i.id = $1 AND i.is_active = 'active'
            GROUP BY i.id
        """

        row = await db.fetchone(query, influencer_id)
        if not row:
            return None

        influencer = self._row_to_influencer(row)
        influencer.conversation_count = int(row["conversation_count"]) if row["conversation_count"] else 0
        return influencer

    def _row_to_influencer(self, row) -> AIInfluencer:
        """Convert database row to AIInfluencer model"""

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

        is_active_value = row["is_active"]
        if isinstance(is_active_value, str):
            try:
                is_active_enum = InfluencerStatus(is_active_value)
            except ValueError:
                is_active_enum = InfluencerStatus.ACTIVE
        else:
            is_active_enum = InfluencerStatus.ACTIVE if is_active_value else InfluencerStatus.DISCONTINUED

        # Extract is_nsfw flag (SQLite stores as 0/1)
        is_nsfw = row.get("is_nsfw", 0)
        is_nsfw_bool = bool(is_nsfw)

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
            is_active=is_active_enum,
            is_nsfw=is_nsfw_bool,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            metadata=metadata,
        )

    async def is_nsfw(self, influencer_id: str) -> bool:
        """Check if an influencer is tagged as NSFW"""
        query = "SELECT is_nsfw FROM ai_influencers WHERE id = $1"
        result = await db.fetchval(query, influencer_id)
        return bool(result) if result is not None else False

    async def list_nsfw(self, limit: int = 50, offset: int = 0) -> list[AIInfluencer]:
        """List all NSFW influencers that are active"""
        query = """
            SELECT
                id, name, display_name, avatar_url, description,
                category, system_instructions, personality_traits,
                initial_greeting, suggested_messages,
                is_active, is_nsfw, created_at, updated_at, metadata
            FROM ai_influencers
            WHERE is_nsfw = 1 AND is_active = 'active'
            ORDER BY created_at DESC
            LIMIT $1 OFFSET $2
        """

        rows = await db.fetch(query, limit, offset)
        return [self._row_to_influencer(row) for row in rows]

    async def count_nsfw(self) -> int:
        """Count all NSFW influencers that are active"""
        query = "SELECT COUNT(*) FROM ai_influencers WHERE is_nsfw = 1 AND is_active = 'active'"
        result = await db.fetchval(query)
        return int(result) if result else 0

    async def create(self, influencer: AIInfluencer) -> AIInfluencer:
        """Create a new influencer"""
        query = """
            INSERT INTO ai_influencers (
                id, name, display_name, avatar_url, description,
                category, system_instructions, personality_traits,
                initial_greeting, suggested_messages,
                is_active, is_nsfw, created_at, updated_at, metadata
            ) VALUES (
                $1, $2, $3, $4, $5,
                $6, $7, $8,
                $9, $10,
                $11, $12, $13, $14, $15
            )
            RETURNING *
        """

        # Serialize dicts/lists to JSON strings
        personality_traits_json = json.dumps(influencer.personality_traits)
        suggested_messages_json = json.dumps(influencer.suggested_messages)
        metadata_json = json.dumps(influencer.metadata)

        # Convert enum/bool to db format
        is_active_str = influencer.is_active.value
        is_nsfw_int = 1 if influencer.is_nsfw else 0

        row = await db.fetchone(
            query,
            influencer.id,
            influencer.name,
            influencer.display_name,
            influencer.avatar_url,
            influencer.description,
            influencer.category,
            influencer.system_instructions,
            personality_traits_json,
            influencer.initial_greeting,
            suggested_messages_json,
            is_active_str,
            is_nsfw_int,
            influencer.created_at,
            influencer.updated_at,
            metadata_json,
        )

        if not row:
            raise RuntimeError("Failed to create influencer")

        return self._row_to_influencer(row)
