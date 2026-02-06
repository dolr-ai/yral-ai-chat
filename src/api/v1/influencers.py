"""AI Influencer endpoints"""
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from src.auth.jwt_auth import CurrentUser, get_current_user
from src.core.dependencies import CharacterGeneratorServiceDep, InfluencerServiceDep
from src.core.moderation import MODERATION_PROMPT, STYLE_PROMPT
from src.models.entities import AIInfluencer, InfluencerStatus
from src.models.requests import (
    CreateInfluencerRequest,
    GeneratePromptRequest,
    UpdateSystemPromptRequest,
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


def _get_user_system_prompt(full_instructions: str | None) -> str | None:
    """Strip STYLE_PROMPT and MODERATION_PROMPT from instructions"""
    if not full_instructions:
        return full_instructions
    
    # The order of appending was: user_prompt + \n + STYLE + \n + MODERATION
    suffix = f"\n{STYLE_PROMPT}\n{MODERATION_PROMPT}"
    if full_instructions.endswith(suffix):
        return full_instructions[: -len(suffix)]
    
    return full_instructions


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
            system_prompt=_get_user_system_prompt(inf.system_instructions),
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
        system_prompt=_get_user_system_prompt(influencer.system_instructions),
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


@router.patch(
    "/{influencer_id}/system-prompt",
    response_model=InfluencerResponse,
    operation_id="updateSystemPrompt",
    summary="Update influencer system prompt",
    description="Update the system prompt for an AI influencer. Only the bot owner (user whose parent_principal_id matches) can perform this action.",
    responses={
        200: {"description": "System prompt updated successfully"},
        401: {"description": "Unauthorized - Missing or invalid authentication"},
        403: {"description": "Forbidden - User is not the bot owner"},
        404: {"description": "Influencer not found"},
        422: {"description": "Validation error - Invalid request data"},
        500: {"description": "Internal server error"},
    },
)
async def update_system_prompt(
    influencer_id: str,
    request: UpdateSystemPromptRequest,
    current_user: CurrentUser = Depends(get_current_user),  # noqa: B008
    influencer_service: InfluencerServiceDep = None,
):
    """Update an influencer's system prompt (bot owner only)"""
    # Get the influencer to check ownership
    influencer = await influencer_service.get_influencer(influencer_id)
    
    # Verify the current user is the bot owner
    if influencer.parent_principal_id != current_user.user_id:
        raise HTTPException(
            status_code=403,
            detail="Only the bot owner can update the system prompt",
        )
    
    # Append style and moderation prompts (same as create endpoint)
    full_system_instructions = f"{request.system_instructions}\n{STYLE_PROMPT}\n{MODERATION_PROMPT}"
    
    # Update the system prompt
    updated = await influencer_service.update_system_prompt(influencer_id, full_system_instructions)
    
    return InfluencerResponse(
        id=updated.id,
        name=updated.name,
        display_name=updated.display_name,
        avatar_url=updated.avatar_url,
        description=updated.description,
        category=updated.category,
        is_active=updated.is_active,
        parent_principal_id=updated.parent_principal_id,
        source=updated.source,
        system_prompt=_get_user_system_prompt(updated.system_instructions),
        created_at=updated.created_at,
    )


@router.delete(
    "/{influencer_id}",
    response_model=InfluencerResponse,
    operation_id="deleteInfluencer",
    summary="Soft delete influencer",
    description="Soft delete an AI influencer by marking it as discontinued and renaming to 'Deleted Bot'. Only the bot owner (user whose parent_principal_id matches) can perform this action. Chat history is preserved.",
    responses={
        200: {"description": "Influencer soft deleted successfully"},
        401: {"description": "Unauthorized - Missing or invalid authentication"},
        403: {"description": "Forbidden - User is not the bot owner"},
        404: {"description": "Influencer not found"},
        500: {"description": "Internal server error"},
    },
)
async def delete_influencer(
    influencer_id: str,
    current_user: CurrentUser = Depends(get_current_user),  # noqa: B008
    influencer_service: InfluencerServiceDep = None,
):
    """Soft delete an influencer (bot owner only)"""
    # Get the influencer to check ownership
    influencer = await influencer_service.get_influencer(influencer_id)
    
    # Verify the current user is the bot owner
    if influencer.parent_principal_id != current_user.user_id:
        raise HTTPException(
            status_code=403,
            detail="Only the bot owner can delete the influencer",
        )
    
    # Soft delete the influencer
    deleted = await influencer_service.soft_delete_influencer(influencer_id)
    
    return InfluencerResponse(
        id=deleted.id,
        name=deleted.name,
        display_name=deleted.display_name,
        avatar_url=deleted.avatar_url,
        description=deleted.description,
        category=deleted.category,
        is_active=deleted.is_active,
        parent_principal_id=deleted.parent_principal_id,
        source=deleted.source,
        system_prompt=_get_user_system_prompt(deleted.system_instructions),
        created_at=deleted.created_at,
    )


