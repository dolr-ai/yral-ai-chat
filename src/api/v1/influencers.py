"""AI Influencer endpoints"""
from datetime import UTC, datetime

from fastapi import APIRouter, Query, Response

from src.core.dependencies import CharacterGeneratorServiceDep, InfluencerServiceDep
from src.core.moderation import MODERATION_PROMPT, STYLE_PROMPT
from src.models.entities import AIInfluencer, InfluencerStatus
from src.models.requests import (
    CreateInfluencerRequest,
    GeneratePromptRequest,
    ValidateMetadataRequest,
)
from src.models.responses import (
    GeneratedMetadataResponse,
    InfluencerCreateResponse,
    InfluencerResponse,
    ListInfluencersResponse,
    SystemPromptResponse,
)

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
    response: Response = None,
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

    # Add cache headers for browser/CDN caching (5 minutes)
    response.headers["Cache-Control"] = "public, max-age=300"

    influencer_responses = [
        InfluencerResponse(
            id=inf.id,
            name=inf.name,
            display_name=inf.display_name,
            avatar_url=inf.avatar_url,
            description=inf.description,
            category=inf.category,
            is_active=inf.is_active,
            parent_principal_id=inf.parent_principal_id,
            source=inf.source,
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
    response: Response = None,
):
    """\
    Get specific AI influencer details
    
    No authentication required
    """
    influencer = await influencer_service.get_influencer(influencer_id)

    # Add cache headers (5 minutes)
    response.headers["Cache-Control"] = "public, max-age=300"

    return InfluencerResponse(
        id=influencer.id,
        name=influencer.name,
        display_name=influencer.display_name,
        avatar_url=influencer.avatar_url,
        description=influencer.description,
        category=influencer.category,
        is_active=influencer.is_active,
        parent_principal_id=influencer.parent_principal_id,
        source=influencer.source,
        created_at=influencer.created_at,
    )


@router.post(
    "/generate-prompt",
    response_model=SystemPromptResponse,
    operation_id="generatePrompt",
    summary="Generate system instructions",
    description="Generate system instructions from a character concept prompt",
)
async def generate_prompt(
    request: GeneratePromptRequest,
    character_generator: CharacterGeneratorServiceDep,
):
    """Generate system instructions"""
    return await character_generator.generate_system_instructions(request.prompt)


@router.post(
    "/validate-and-generate-metadata",
    response_model=GeneratedMetadataResponse,
    operation_id="validateAndGenerateMetadata",
    summary="Validate instructions and generate metadata",
    description="Validate system instructions and generate metadata + avatar",
)
async def validate_and_generate_metadata(
    request: ValidateMetadataRequest,
    character_generator: CharacterGeneratorServiceDep,
):
    """Validate system instructions and generate metadata using AI"""
    return await character_generator.validate_and_generate_metadata(request.system_instructions)


@router.post(
    "/create",
    response_model=InfluencerCreateResponse,
    operation_id="createInfluencer",
    summary="Create a new influencer",
    description="Create a new AI influencer character",
)
async def create_influencer(
    request: CreateInfluencerRequest,
    influencer_service: InfluencerServiceDep,
    character_generator_service: CharacterGeneratorServiceDep,
):
    """Create a new AI influencer"""
    influencer = AIInfluencer(
        id=request.bot_principal_id,
        name=request.name,
        display_name=request.display_name,
        avatar_url=request.avatar_url,
        description=request.description,
        category=request.category,
        system_instructions=f"{request.system_instructions}\n{STYLE_PROMPT}\n{MODERATION_PROMPT}",
        personality_traits=request.personality_traits,
        initial_greeting=request.initial_greeting,
        suggested_messages=request.suggested_messages,
        is_active=InfluencerStatus.ACTIVE,
        is_nsfw=False,  # Enforce non-NSFW for all new characters
        parent_principal_id=request.parent_principal_id,
        source="user-created-influencer" if request.parent_principal_id else "admin-created-influencer",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        metadata={},
    )

    created = await influencer_service.create_influencer(influencer)

    # Generate starter video prompt (not stored in DB)
    starter_video_prompt = await character_generator_service.generate_starter_video_prompt(
        display_name=created.display_name,
        system_instructions=request.system_instructions,
    )

    return InfluencerCreateResponse(
        id=created.id,
        name=created.name,
        display_name=created.display_name,
        avatar_url=created.avatar_url,
        description=created.description,
        category=created.category,
        is_active=created.is_active,
        parent_principal_id=created.parent_principal_id,
        source=created.source,
        starter_video_prompt=starter_video_prompt,
        created_at=created.created_at,
    )
