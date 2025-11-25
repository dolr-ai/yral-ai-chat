"""
AI Influencer endpoints
"""
from fastapi import APIRouter, Query
from uuid import UUID
from src.models.responses import InfluencerResponse, ListInfluencersResponse
from src.services.influencer_service import influencer_service

router = APIRouter(prefix="/api/v1/influencers", tags=["Influencers"])


@router.get("", response_model=ListInfluencersResponse)
async def list_influencers(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0)
):
    """
    List all active AI influencers
    
    No authentication required for discovery
    """
    influencers, total = await influencer_service.list_influencers(
        limit=limit,
        offset=offset
    )
    
    # Convert to response models
    influencer_responses = [
        InfluencerResponse(
            id=inf.id,
            name=inf.name,
            display_name=inf.display_name,
            avatar_url=inf.avatar_url,
            description=inf.description,
            category=inf.category,
            created_at=inf.created_at
        )
        for inf in influencers
    ]
    
    return ListInfluencersResponse(
        influencers=influencer_responses,
        total=total,
        limit=limit,
        offset=offset
    )


@router.get("/{influencer_id}", response_model=InfluencerResponse)
async def get_influencer(influencer_id: UUID):
    """
    Get specific AI influencer details
    
    No authentication required
    """
    influencer = await influencer_service.get_influencer(influencer_id)
    
    return InfluencerResponse(
        id=influencer.id,
        name=influencer.name,
        display_name=influencer.display_name,
        avatar_url=influencer.avatar_url,
        description=influencer.description,
        category=influencer.category,
        created_at=influencer.created_at,
        conversation_count=influencer.conversation_count
    )


