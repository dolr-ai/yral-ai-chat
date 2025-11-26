"""
Influencer service - Business logic for AI influencers
"""
from typing import List
from uuid import UUID
from src.db.repositories import InfluencerRepository
from src.models.entities import AIInfluencer
from src.core.exceptions import NotFoundException


class InfluencerService:
    """Service for influencer operations"""
    
    def __init__(self):
        self.influencer_repo = InfluencerRepository()
    
    async def list_influencers(
        self,
        limit: int = 50,
        offset: int = 0
    ) -> tuple[List[AIInfluencer], int]:
        """List all active influencers"""
        influencers = await self.influencer_repo.list_all(limit=limit, offset=offset)
        total = await self.influencer_repo.count_all()
        return influencers, total
    
    async def get_influencer(self, influencer_id: UUID) -> AIInfluencer:
        """Get influencer by ID with conversation count"""
        influencer = await self.influencer_repo.get_with_conversation_count(influencer_id)
        if not influencer:
            raise NotFoundException("Influencer not found")
        return influencer


# Global influencer service instance
influencer_service = InfluencerService()


