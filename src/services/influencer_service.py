"""
Influencer service - Business logic for AI influencers
"""
from src.core.cache import cached
from src.core.exceptions import NotFoundException
from src.db.repositories import InfluencerRepository
from src.models.entities import AIInfluencer


class InfluencerService:
    """Service for influencer operations"""

    def __init__(self, influencer_repo: InfluencerRepository):
        self.influencer_repo = influencer_repo

    @cached(ttl=600, key_prefix="influencers")  # Cache for 10 minutes
    async def list_influencers(
        self,
        limit: int = 50,
        offset: int = 0
    ) -> tuple[list[AIInfluencer], int]:
        """List all influencers (active and inactive, cached)"""
        influencers = await self.influencer_repo.list_all(limit=limit, offset=offset)
        total = await self.influencer_repo.count_all()
        return influencers, total

    @cached(ttl=300, key_prefix="influencer")  # Cache for 5 minutes
    async def get_influencer(self, influencer_id: str) -> AIInfluencer:
        """Get influencer by ID with conversation count (cached)"""
        influencer = await self.influencer_repo.get_with_conversation_count(influencer_id)
        if not influencer:
            raise NotFoundException("Influencer not found")
        return influencer

