"""
Influencer service - Business logic for AI influencers
"""

from pydantic import validate_call

from src.core.cache import cached
from src.core.exceptions import NotFoundException
from src.db.repositories import InfluencerRepository
from src.models.entities import AIInfluencer


class InfluencerService:
    """Service for influencer operations"""

    def __init__(self, influencer_repo: InfluencerRepository):
        self.influencer_repo = influencer_repo

    @validate_call
    @cached(ttl=120, key_prefix="influencers")  # Reduced from 600 to 120 to mitigate multi-worker staleness
    async def list_influencers(self, limit: int = 50, offset: int = 0) -> tuple[list[AIInfluencer], int]:
        """List all influencers (active and inactive, cached)"""
        influencers = await self.influencer_repo.list_all(limit=limit, offset=offset)

        total = await self.influencer_repo.count_all()
        return influencers, total

    @validate_call
    @cached(ttl=120, key_prefix="influencer")  # Reduced from 300 to 120 to mitigate multi-worker staleness
    async def get_influencer(self, influencer_id: str) -> AIInfluencer:
        """Get influencer by ID with conversation count (cached)"""
        influencer = await self.influencer_repo.get_with_conversation_count(influencer_id)
        if not influencer:
            raise NotFoundException("Influencer not found")
        return influencer

    @validate_call
    @cached(ttl=600, key_prefix="is_nsfw")  # Cache for 10 minutes
    async def is_nsfw(self, influencer_id: str) -> bool:
        """Check if an influencer is tagged as NSFW"""
        return await self.influencer_repo.is_nsfw(influencer_id)

    @validate_call
    @cached(ttl=600, key_prefix="nsfw_influencers")  # Cache for 10 minutes
    async def list_nsfw_influencers(self, limit: int = 50, offset: int = 0) -> tuple[list[AIInfluencer], int]:
        """List all NSFW influencers (cached)"""
        influencers = await self.influencer_repo.list_nsfw(limit=limit, offset=offset)
        total = await self.influencer_repo.count_nsfw()
        return influencers, total

    @validate_call(config={"arbitrary_types_allowed": True})
    async def get_ai_provider_for_influencer(self, influencer: AIInfluencer) -> str:
        """
        Determine which AI provider should be used for this influencer

        Args:
            influencer: The influencer entity

        Returns:
            "openrouter" for NSFW influencers, "gemini" otherwise
        """
        return "openrouter" if influencer.is_nsfw else "gemini"

    @validate_call(config={"arbitrary_types_allowed": True})
    async def create_influencer(self, influencer: AIInfluencer) -> AIInfluencer:
        """Create a new influencer and clear cache"""
        created = await self.influencer_repo.create(influencer)
        # Clear caches
        self.list_influencers.invalidate_all()
        if created.is_nsfw:
            self.list_nsfw_influencers.invalidate_all()
        return created

    @validate_call
    async def update_system_prompt(self, influencer_id: str, system_instructions: str) -> AIInfluencer:
        """Update influencer system prompt and clear caches"""
        updated = await self.influencer_repo.update_system_prompt(influencer_id, system_instructions)
        if not updated:
            raise NotFoundException("Influencer not found")

        # Clear caches
        self.get_influencer.invalidate_all()
        self.list_influencers.invalidate_all()
        if updated.is_nsfw:
            self.list_nsfw_influencers.invalidate_all()

        return updated

    @validate_call
    @cached(ttl=600, key_prefix="trending_influencers")  # Cache for 10 minutes
    async def list_trending_influencers(self, limit: int = 50, offset: int = 0) -> tuple[list[AIInfluencer], int]:
        """List influencers sorted by total message count (cached)"""
        influencers = await self.influencer_repo.list_trending(limit=limit, offset=offset)
        # We use a simplified count for trending (all influencers by default or reuse count_all)
        total = await self.influencer_repo.count_all()
        return influencers, total

    @validate_call
    async def soft_delete_influencer(self, influencer_id: str) -> AIInfluencer:
        """Soft delete influencer (mark as discontinued, rename to 'Deleted Bot') and clear caches"""
        deleted = await self.influencer_repo.soft_delete(influencer_id)
        if not deleted:
            raise NotFoundException("Influencer not found")

        # Clear caches
        self.get_influencer.invalidate_all()
        self.list_influencers.invalidate_all()
        self.list_trending_influencers.invalidate_all()
        if deleted.is_nsfw:
            self.list_nsfw_influencers.invalidate_all()

        return deleted
