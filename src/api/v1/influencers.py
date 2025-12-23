"""
AI Influencer endpoints
"""
from fastapi import APIRouter, Query

from src.core.dependencies import InfluencerServiceDep
from src.models.responses import InfluencerResponse, ListInfluencersResponse

router = APIRouter(prefix="/api/v1/influencers", tags=["Influencers"])


@router.get(
    "",
    response_model=ListInfluencersResponse,
    operation_id="listInfluencers",
    summary="List AI influencers",
    description="Retrieve paginated list of all AI influencers. Influencers are ordered by status (active, coming_soon, discontinued) with active influencers listed first. No authentication required.",
    responses={
        200: {"description": "List of influencers retrieved successfully"},
        422: {"description": "Validation error - Invalid query parameters"},
        429: {"description": "Rate limit exceeded"},
        500: {"description": "Internal server error"},
    },
)
async def list_influencers(
    limit: int = Query(default=50, ge=1, le=100, description="Number of influencers to return"),
    offset: int = Query(default=0, ge=0, description="Number of influencers to skip"),
    influencer_service: InfluencerServiceDep = None,
):
    """\
    List all AI influencers
    
    Influencers are ordered by status: active, coming_soon, then discontinued.
    Active influencers are listed first.
    No authentication required for discovery.
    """
    influencers, total = await influencer_service.list_influencers(
        limit=limit,
        offset=offset,
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
            is_active=inf.is_active,
            created_at=inf.created_at,
        )
        for inf in influencers
    ]

    return ListInfluencersResponse(
        influencers=influencer_responses,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{influencer_id}",
    response_model=InfluencerResponse,
    operation_id="getInfluencer",
    summary="Get influencer details",
    description="Retrieve detailed information about a specific AI influencer. No authentication required.",
    responses={
        200: {"description": "Influencer details retrieved successfully"},
        404: {"description": "Influencer not found"},
        422: {"description": "Validation error - Invalid influencer ID format"},
        429: {"description": "Rate limit exceeded"},
        500: {"description": "Internal server error"},
    },
)
async def get_influencer(
    influencer_id: str,
    influencer_service: InfluencerServiceDep = None,
):
    """\
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
        is_active=influencer.is_active,
        created_at=influencer.created_at,
    )


