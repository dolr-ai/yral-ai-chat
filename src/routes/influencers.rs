use std::sync::Arc;

use axum::Json;
use axum::extract::{Path, Query, State};
use axum::http::header;
use validator::Validate;

use crate::AppState;
use crate::db::repositories::InfluencerRepository;
use crate::error::AppError;
use crate::middleware::AuthenticatedUser;
use crate::models::entities::{AIInfluencer, InfluencerStatus};
use crate::models::requests::{
    CreateInfluencerRequest, GeneratePromptRequest, PaginationParams, UpdateSystemPromptRequest,
    ValidateMetadataRequest,
};
use crate::models::responses::{
    GeneratedMetadataResponse, InfluencerResponse, ListInfluencersResponse,
    ListTrendingInfluencersResponse, SystemPromptResponse, TrendingInfluencerResponse,
};
use crate::services::character_generator::CharacterGeneratorService;
use crate::services::moderation;

impl From<AIInfluencer> for InfluencerResponse {
    fn from(i: AIInfluencer) -> Self {
        Self {
            id: i.id,
            name: i.name,
            display_name: i.display_name,
            avatar_url: i.avatar_url,
            description: i.description,
            category: i.category,
            is_active: i.is_active,
            parent_principal_id: i.parent_principal_id,
            source: i.source,
            system_prompt: Some(moderation::strip_guardrails(&i.system_instructions)),
            created_at: i.created_at,
            conversation_count: i.conversation_count,
            message_count: i.message_count,
            starter_video_prompt: None,
        }
    }
}

type CachedJson<T> = ([(header::HeaderName, &'static str); 1], Json<T>);

// GET /api/v1/influencers
pub async fn list_influencers(
    State(state): State<Arc<AppState>>,
    Query(params): Query<PaginationParams>,
) -> Result<CachedJson<ListInfluencersResponse>, AppError> {
    let repo = InfluencerRepository::new(state.db.pool.clone());

    let limit = params.limit(50, 100);
    let offset = params.offset();

    let (influencers, total) = tokio::try_join!(repo.list_all(limit, offset), repo.count_all(),)?;

    Ok((
        [(header::CACHE_CONTROL, "public, max-age=300")],
        Json(ListInfluencersResponse {
            influencers: influencers
                .into_iter()
                .map(InfluencerResponse::from)
                .collect(),
            total,
            limit,
            offset,
        }),
    ))
}

// GET /api/v1/influencers/trending
pub async fn list_trending(
    State(state): State<Arc<AppState>>,
    Query(params): Query<PaginationParams>,
) -> Result<CachedJson<ListTrendingInfluencersResponse>, AppError> {
    let repo = InfluencerRepository::new(state.db.pool.clone());

    let limit = params.limit(50, 100);
    let offset = params.offset();

    let (influencers, total) =
        tokio::try_join!(repo.list_trending(limit, offset), repo.count_trending(),)?;

    let influencers = influencers
        .into_iter()
        .map(|i| TrendingInfluencerResponse {
            id: i.id,
            name: i.name,
            display_name: i.display_name,
            avatar_url: i.avatar_url,
            description: i.description,
            category: i.category,
            is_active: i.is_active,
            created_at: i.created_at,
            conversation_count: i.conversation_count.unwrap_or(0),
            message_count: i.message_count.unwrap_or(0),
        })
        .collect();

    Ok((
        [(header::CACHE_CONTROL, "public, max-age=300")],
        Json(ListTrendingInfluencersResponse {
            influencers,
            total,
            limit,
            offset,
        }),
    ))
}

// GET /api/v1/influencers/{influencer_id}
pub async fn get_influencer(
    State(state): State<Arc<AppState>>,
    Path(influencer_id): Path<String>,
) -> Result<CachedJson<InfluencerResponse>, AppError> {
    let repo = InfluencerRepository::new(state.db.pool.clone());

    let influencer = repo
        .get_with_conversation_count(&influencer_id)
        .await?
        .ok_or_else(|| AppError::not_found(format!("Influencer '{influencer_id}' not found")))?;

    Ok((
        [(header::CACHE_CONTROL, "public, max-age=300")],
        Json(InfluencerResponse::from(influencer)),
    ))
}

// POST /api/v1/influencers/generate-prompt
pub async fn generate_prompt(
    State(state): State<Arc<AppState>>,
    _user: AuthenticatedUser,
    Json(body): Json<GeneratePromptRequest>,
) -> Result<Json<SystemPromptResponse>, AppError> {
    let instructions =
        CharacterGeneratorService::generate_system_instructions(&state.gemini, &body.prompt)
            .await?;

    Ok(Json(SystemPromptResponse {
        system_instructions: instructions,
    }))
}

// POST /api/v1/influencers/validate-and-generate-metadata
pub async fn validate_and_generate_metadata(
    State(state): State<Arc<AppState>>,
    _user: AuthenticatedUser,
    Json(body): Json<ValidateMetadataRequest>,
) -> Result<Json<GeneratedMetadataResponse>, AppError> {
    let result = CharacterGeneratorService::validate_and_generate_metadata(
        &state.gemini,
        &state.replicate,
        &body.system_instructions,
    )
    .await?;

    Ok(Json(result))
}

// POST /api/v1/influencers/create
pub async fn create_influencer(
    State(state): State<Arc<AppState>>,
    user: AuthenticatedUser,
    Json(body): Json<CreateInfluencerRequest>,
) -> Result<Json<InfluencerResponse>, AppError> {
    // Validate request body
    body.validate()
        .map_err(|e| AppError::validation_error(format!("{e}")))?;

    let repo = InfluencerRepository::new(state.db.pool.clone());

    // Check name uniqueness
    if let Some(_existing) = repo.get_by_name(&body.name).await? {
        return Err(AppError::conflict(format!(
            "Influencer name '{}' already exists",
            body.name
        )));
    }

    // Append moderation guardrails
    let system_instructions = moderation::with_guardrails(&body.system_instructions);

    // Generate greeting if not provided
    let (initial_greeting, suggested_messages) = if body.initial_greeting.is_some() {
        (
            body.initial_greeting.clone(),
            if body.suggested_messages.is_empty() {
                vec![]
            } else {
                body.suggested_messages.clone()
            },
        )
    } else {
        match CharacterGeneratorService::generate_initial_greeting(
            &state.gemini,
            &body.display_name,
            &body.system_instructions,
        )
        .await
        {
            Ok((greeting, suggestions)) => (Some(greeting), suggestions),
            Err(e) => {
                tracing::error!(error = %e, "Failed to generate greeting");
                (
                    Some(format!(
                        "Hey! I'm {}! How can I help you today?",
                        body.display_name
                    )),
                    vec![],
                )
            }
        }
    };

    // Always use the authenticated user's ID (security: prevent override)
    let parent_principal_id = user.user_id.clone();

    let now = chrono::Utc::now().naive_utc();
    let influencer = AIInfluencer {
        id: body.bot_principal_id.clone(),
        name: body.name,
        display_name: body.display_name.clone(),
        avatar_url: body.avatar_url,
        description: body.description,
        category: body.category,
        system_instructions,
        personality_traits: body.personality_traits,
        initial_greeting,
        suggested_messages,
        is_active: InfluencerStatus::Active,
        is_nsfw: false, // enforced
        parent_principal_id: Some(parent_principal_id),
        source: Some("user-created-influencer".to_string()),
        created_at: now,
        updated_at: now,
        metadata: serde_json::json!({}),
        conversation_count: None,
        message_count: None,
    };

    repo.create(&influencer).await?;

    // Generate starter video prompt in parallel (best-effort)
    let starter_video_prompt = match CharacterGeneratorService::generate_starter_video_prompt(
        &state.gemini,
        &body.display_name,
        &body.system_instructions,
    )
    .await
    {
        Ok(prompt) => Some(prompt),
        Err(e) => {
            tracing::error!(error = %e, "Failed to generate starter video prompt");
            None
        }
    };

    let mut resp = InfluencerResponse::from(influencer);
    resp.starter_video_prompt = starter_video_prompt;

    Ok(Json(resp))
}

// PATCH /api/v1/influencers/{influencer_id}/system-prompt
pub async fn update_system_prompt(
    State(state): State<Arc<AppState>>,
    user: AuthenticatedUser,
    Path(influencer_id): Path<String>,
    Json(body): Json<UpdateSystemPromptRequest>,
) -> Result<Json<InfluencerResponse>, AppError> {
    let repo = InfluencerRepository::new(state.db.pool.clone());

    let influencer = repo
        .get_by_id(&influencer_id)
        .await?
        .ok_or_else(|| AppError::not_found("Influencer not found"))?;

    // Only the owner can update
    if influencer.parent_principal_id.as_deref() != Some(&user.user_id) {
        return Err(AppError::forbidden(
            "Only the bot owner can update system prompt",
        ));
    }

    let instructions = moderation::with_guardrails(&body.system_instructions);
    repo.update_system_prompt(&influencer_id, &instructions)
        .await?;

    let updated = repo
        .get_by_id(&influencer_id)
        .await?
        .ok_or_else(|| AppError::not_found("Influencer not found"))?;

    Ok(Json(InfluencerResponse::from(updated)))
}

// DELETE /api/v1/influencers/{influencer_id}
pub async fn delete_influencer(
    State(state): State<Arc<AppState>>,
    user: AuthenticatedUser,
    Path(influencer_id): Path<String>,
) -> Result<Json<InfluencerResponse>, AppError> {
    let repo = InfluencerRepository::new(state.db.pool.clone());

    let influencer = repo
        .get_by_id(&influencer_id)
        .await?
        .ok_or_else(|| AppError::not_found("Influencer not found"))?;

    // Only the owner can delete
    if influencer.parent_principal_id.as_deref() != Some(&user.user_id) {
        return Err(AppError::forbidden(
            "Only the bot owner can delete this bot",
        ));
    }

    repo.soft_delete(&influencer_id).await?;

    let updated = repo
        .get_by_id(&influencer_id)
        .await?
        .ok_or_else(|| AppError::not_found("Influencer not found"))?;

    Ok(Json(InfluencerResponse::from(updated)))
}
