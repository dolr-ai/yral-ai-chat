use std::sync::Arc;

use axum::Json;
use axum::extract::{Path, Query, State};
use axum::http::{HeaderMap, header};
use validator::Validate;

use crate::AppState;
use crate::error::{AppError, ErrorBody};
use crate::middleware::AuthenticatedUser;
use crate::models::entities::{AIInfluencer, InfluencerStatus};
use crate::models::requests::{
    CreateInfluencerRequest, GeneratePromptRequest, GenerateVideoPromptRequest, PaginationParams,
    UpdateSystemPromptRequest, ValidateMetadataRequest,
};
use crate::models::responses::{
    GeneratedMetadataResponse, InfluencerResponse, ListInfluencersResponse,
    ListTrendingInfluencersResponse, SystemPromptResponse, TrendingInfluencerResponse,
    VideoPromptResponse,
};
use crate::services::character_generator::CharacterGeneratorService;
use crate::services::moderation;

/// Fetch profile picture from User Info Service canister for main user accounts
async fn fetch_user_profile_pic(agent: &ic_agent::Agent, principal_id: &str) -> Option<String> {
    let principal = candid::Principal::from_text(principal_id).ok()?;

    let canister_id = yral_canisters_client::ic::USER_INFO_SERVICE_ID;
    let service = yral_canisters_client::user_info_service::UserInfoService(canister_id, agent);

    match service.get_users_profile_details(vec![principal]).await {
        Ok(yral_canisters_client::user_info_service::Result9::Ok(details)) => details
            .into_iter()
            .next()
            .and_then(|d| d.profile_picture.map(|p| p.url)),
        Ok(yral_canisters_client::user_info_service::Result9::Err(e)) => {
            tracing::warn!(error = %e, "Canister error fetching user profile");
            None
        }
        Err(e) => {
            tracing::warn!(error = %e, "IC agent error fetching user profile");
            None
        }
    }
}

/// Fetch username from metadata server for main user accounts
async fn fetch_username_from_metadata(
    http_client: &reqwest::Client,
    metadata_url: &str,
    principal_id: &str,
) -> Option<String> {
    let url = format!(
        "{}/user-profile/{}?user_id={}",
        metadata_url.trim_end_matches('/'),
        principal_id,
        principal_id
    );

    match http_client.get(&url).send().await {
        Ok(resp) => {
            if !resp.status().is_success() {
                tracing::warn!(status = %resp.status(), "Metadata server returned error for user profile");
                return None;
            }
            match resp.json::<serde_json::Value>().await {
                Ok(json) => json
                    .get("Ok")
                    .and_then(|v| v.get("user_name"))
                    .and_then(|v| v.as_str())
                    .map(|s| s.to_string()),
                Err(e) => {
                    tracing::warn!(error = %e, "Failed to parse metadata user profile response");
                    None
                }
            }
        }
        Err(e) => {
            tracing::warn!(error = %e, "Failed to fetch username from metadata server");
            None
        }
    }
}

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

/// List all influencers
#[utoipa::path(
    get,
    path = "/api/v1/influencers",
    params(PaginationParams),
    responses(
        (status = 200, body = ListInfluencersResponse, description = "Successful response"),
        (status = 422, body = ErrorBody, description = "Validation error")
    ),
    tag = "Influencers"
)]
pub async fn list_influencers(
    State(state): State<Arc<AppState>>,
    Query(params): Query<PaginationParams>,
) -> Result<CachedJson<ListInfluencersResponse>, AppError> {
    let repo = state.db.inf_repo();

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

/// List trending influencers
#[utoipa::path(
    get,
    path = "/api/v1/influencers/trending",
    params(PaginationParams),
    responses(
        (status = 200, body = ListTrendingInfluencersResponse, description = "Successful response"),
        (status = 422, body = ErrorBody, description = "Validation error")
    ),
    tag = "Influencers"
)]
pub async fn list_trending(
    State(state): State<Arc<AppState>>,
    Query(params): Query<PaginationParams>,
) -> Result<CachedJson<ListTrendingInfluencersResponse>, AppError> {
    let repo = state.db.inf_repo();

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

/// Get an influencer by ID
#[utoipa::path(
    get,
    path = "/api/v1/influencers/{influencer_id}",
    params(("influencer_id" = String, Path, description = "Influencer ID")),
    responses(
        (status = 200, body = InfluencerResponse),
        (status = 404, body = ErrorBody)
    ),
    tag = "Influencers"
)]
pub async fn get_influencer(
    State(state): State<Arc<AppState>>,
    Path(influencer_id): Path<String>,
) -> Result<CachedJson<InfluencerResponse>, AppError> {
    let repo = state.db.inf_repo();

    let influencer = repo
        .get_with_conversation_count(&influencer_id)
        .await?
        .ok_or_else(|| AppError::not_found(format!("Influencer '{influencer_id}' not found")))?;

    Ok((
        [(header::CACHE_CONTROL, "public, max-age=300")],
        Json(InfluencerResponse::from(influencer)),
    ))
}

/// Generate a system prompt from a user description
#[utoipa::path(
    post,
    path = "/api/v1/influencers/generate-prompt",
    request_body = GeneratePromptRequest,
    responses(
        (status = 200, body = SystemPromptResponse, description = "Successful response"),
        (status = 401, body = ErrorBody, description = "Unauthorized"),
        (status = 422, body = ErrorBody, description = "Validation error")
    ),
    tag = "Influencers",
    security(("BearerAuth" = []))
)]
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

/// Validate system instructions and generate influencer metadata
#[utoipa::path(
    post,
    path = "/api/v1/influencers/validate-and-generate-metadata",
    request_body = ValidateMetadataRequest,
    responses(
        (status = 200, body = GeneratedMetadataResponse, description = "Successful response"),
        (status = 401, body = ErrorBody, description = "Unauthorized"),
        (status = 422, body = ErrorBody, description = "Validation error")
    ),
    tag = "Influencers",
    security(("BearerAuth" = []))
)]
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

/// Create a new AI influencer
#[utoipa::path(
    post,
    path = "/api/v1/influencers/create",
    request_body = CreateInfluencerRequest,
    responses(
        (status = 200, body = InfluencerResponse, description = "Successful response"),
        (status = 401, body = ErrorBody, description = "Unauthorized"),
        (status = 409, body = ErrorBody, description = "Conflict"),
        (status = 422, body = ErrorBody, description = "Validation error")
    ),
    tag = "Influencers",
    security(("BearerAuth" = []))
)]
pub async fn create_influencer(
    State(state): State<Arc<AppState>>,
    user: AuthenticatedUser,
    Json(body): Json<CreateInfluencerRequest>,
) -> Result<Json<InfluencerResponse>, AppError> {
    // Validate request body
    body.validate()
        .map_err(|e| AppError::validation_error(format!("{e}")))?;

    let repo = state.db.inf_repo();

    // Check name uniqueness
    if let Some(_existing) = repo.get_by_name(&body.name).await? {
        return Err(AppError::conflict(format!(
            "Influencer name '{}' already exists",
            body.name
        )));
    }

    // Append moderation guardrails
    let system_instructions = moderation::with_guardrails(&body.system_instructions);

    // Generate greeting/suggestions if either is missing (matches Python behavior)
    let mut initial_greeting = body.initial_greeting.clone();
    let mut suggested_messages = body.suggested_messages.clone();

    if initial_greeting.is_none() || suggested_messages.is_empty() {
        match CharacterGeneratorService::generate_initial_greeting(
            &state.gemini,
            &body.display_name,
            &body.system_instructions,
        )
        .await
        {
            Ok((gen_greeting, gen_suggestions)) => {
                if initial_greeting.is_none() {
                    initial_greeting = Some(gen_greeting);
                }
                if suggested_messages.is_empty() {
                    suggested_messages = gen_suggestions;
                }
            }
            Err(e) => {
                tracing::error!(error = %e, "Failed to generate greeting");
                if initial_greeting.is_none() {
                    initial_greeting = Some(format!(
                        "Hey! I'm {}! How can I help you today?",
                        body.display_name
                    ));
                }
            }
        }
    }

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

/// Update an influencer's system prompt
#[utoipa::path(
    patch,
    path = "/api/v1/influencers/{influencer_id}/system-prompt",
    params(("influencer_id" = String, Path, description = "Influencer ID")),
    request_body = UpdateSystemPromptRequest,
    responses(
        (status = 200, body = InfluencerResponse, description = "Successful response"),
        (status = 401, body = ErrorBody, description = "Unauthorized"),
        (status = 403, body = ErrorBody, description = "Forbidden"),
        (status = 404, body = ErrorBody, description = "Not found"),
        (status = 422, body = ErrorBody, description = "Validation error")
    ),
    tag = "Influencers",
    security(("BearerAuth" = []))
)]
pub async fn update_system_prompt(
    State(state): State<Arc<AppState>>,
    user: AuthenticatedUser,
    Path(influencer_id): Path<String>,
    Json(body): Json<UpdateSystemPromptRequest>,
) -> Result<Json<InfluencerResponse>, AppError> {
    let repo = state.db.inf_repo();

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

/// Generate a video prompt for subsequent bot videos
/// This endpoint creates an LTX-optimized video prompt with full context from the bot's system instructions
#[utoipa::path(
    post,
    path = "/api/v1/influencers/{influencer_id}/generate-video-prompt",
    params(("influencer_id" = String, Path, description = "Influencer ID")),
    request_body = GenerateVideoPromptRequest,
    responses(
        (status = 200, body = VideoPromptResponse, description = "Successful response"),
        (status = 401, body = ErrorBody, description = "Unauthorized"),
        (status = 404, body = ErrorBody, description = "Not found"),
        (status = 422, body = ErrorBody, description = "Validation error")
    ),
    tag = "Influencers",
    security(("BearerAuth" = []))
)]
pub async fn generate_video_prompt(
    State(state): State<Arc<AppState>>,
    _user: AuthenticatedUser,
    Path(influencer_id): Path<String>,
    Json(body): Json<GenerateVideoPromptRequest>,
) -> Result<Json<VideoPromptResponse>, AppError> {
    // Validate request body
    body.validate()
        .map_err(|e| AppError::validation_error(format!("{e}")))?;

    let repo = state.db.inf_repo();

    // Try to get the influencer - if not found, try to fetch profile from canister for main accounts
    let video_prompt = match repo.get_by_id(&influencer_id).await? {
        Some(influencer) => {
            // Bot context available - generate prompt with bot's system instructions
            let system_instructions = moderation::strip_guardrails(&influencer.system_instructions);
            CharacterGeneratorService::generate_subsequent_video_prompt(
                &state.gemini,
                &influencer.display_name,
                &system_instructions,
                &body.scene_description,
                influencer.avatar_url.as_deref(),
                body.reference_image_url.as_deref(),
            )
            .await?
        }
        None => {
            // Not a bot - fetch profile info for main user account
            let (avatar_url, username) = tokio::join!(
                fetch_user_profile_pic(&state.ic_agent, &influencer_id),
                fetch_username_from_metadata(
                    &state.http_client,
                    &state.settings.metadata_url,
                    &influencer_id
                )
            );

            // Use username from metadata, or fallback to short principal
            let display_name = username.unwrap_or_else(|| {
                format!("User {}", &influencer_id[..8.min(influencer_id.len())])
            });

            // Generate base prompt with avatar (if found) since main accounts don't have system instructions
            CharacterGeneratorService::generate_base_video_prompt(
                &state.gemini,
                &display_name,
                &body.scene_description,
                avatar_url.as_deref(),
                body.reference_image_url.as_deref(),
            )
            .await?
        }
    };

    Ok(Json(VideoPromptResponse {
        video_prompt,
        scene_description: body.scene_description,
    }))
}

/// Delete an influencer (soft delete) — owner only
#[utoipa::path(
    delete,
    path = "/api/v1/influencers/{influencer_id}",
    params(("influencer_id" = String, Path, description = "Influencer ID")),
    responses(
        (status = 200, body = InfluencerResponse, description = "Successful response"),
        (status = 401, body = ErrorBody, description = "Unauthorized"),
        (status = 403, body = ErrorBody, description = "Forbidden"),
        (status = 404, body = ErrorBody, description = "Not found")
    ),
    tag = "Influencers",
    security(("BearerAuth" = []))
)]
pub async fn delete_influencer(
    State(state): State<Arc<AppState>>,
    user: AuthenticatedUser,
    Path(influencer_id): Path<String>,
) -> Result<Json<InfluencerResponse>, AppError> {
    let repo = state.db.inf_repo();

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

/// Ban an influencer (admin only) — requires X-Admin-Key header
#[utoipa::path(
    delete,
    path = "/api/v1/admin/influencers/{influencer_id}",
    params(("influencer_id" = String, Path, description = "Influencer ID")),
    responses(
        (status = 200, body = InfluencerResponse, description = "Influencer banned"),
        (status = 401, body = ErrorBody, description = "Missing or invalid admin key"),
        (status = 404, body = ErrorBody, description = "Not found")
    ),
    tag = "Admin"
)]
pub async fn admin_ban_influencer(
    State(state): State<Arc<AppState>>,
    headers: HeaderMap,
    Path(influencer_id): Path<String>,
) -> Result<Json<InfluencerResponse>, AppError> {
    let provided_key = headers
        .get("X-Admin-Key")
        .and_then(|v| v.to_str().ok())
        .unwrap_or("");

    let valid = state
        .settings
        .admin_key_to_delete_influencer
        .as_deref()
        .is_some_and(|key| provided_key == key);

    if !valid {
        return Err(AppError::unauthorized("Invalid or missing admin key"));
    }

    let repo = state.db.inf_repo();

    let influencer = repo
        .get_by_id_or_name(&influencer_id)
        .await?
        .ok_or_else(|| AppError::not_found("Influencer not found"))?;

    if let Err(e) = repo.ban(&influencer.id).await {
        state
            .google_chat
            .notify_influencer_ban_failed(&influencer.id, &e.to_string())
            .await;
        return Err(e.into());
    }

    state
        .google_chat
        .notify_influencer_banned(&influencer.id, &influencer.name)
        .await;

    Ok(Json(InfluencerResponse::from(influencer)))
}

/// Unban an influencer (admin only) — requires X-Admin-Key header
#[utoipa::path(
    post,
    path = "/api/v1/admin/influencers/{influencer_id}/unban",
    params(("influencer_id" = String, Path, description = "Influencer ID")),
    responses(
        (status = 200, body = InfluencerResponse, description = "Influencer unbanned"),
        (status = 401, body = ErrorBody, description = "Missing or invalid admin key"),
        (status = 404, body = ErrorBody, description = "Not found")
    ),
    tag = "Admin"
)]
pub async fn admin_unban_influencer(
    State(state): State<Arc<AppState>>,
    headers: HeaderMap,
    Path(influencer_id): Path<String>,
) -> Result<Json<InfluencerResponse>, AppError> {
    let provided_key = headers
        .get("X-Admin-Key")
        .and_then(|v| v.to_str().ok())
        .unwrap_or("");

    let valid = state
        .settings
        .admin_key_to_delete_influencer
        .as_deref()
        .is_some_and(|key| provided_key == key);

    if !valid {
        return Err(AppError::unauthorized("Invalid or missing admin key"));
    }

    let repo = state.db.inf_repo();

    let influencer = repo
        .get_by_id_or_name(&influencer_id)
        .await?
        .ok_or_else(|| AppError::not_found("Influencer not found"))?;

    if let Err(e) = repo.unban(&influencer.id).await {
        state
            .google_chat
            .notify_influencer_unban_failed(&influencer.id, &e.to_string())
            .await;
        return Err(e.into());
    }

    state
        .google_chat
        .notify_influencer_unbanned(&influencer.id, &influencer.name)
        .await;

    Ok(Json(InfluencerResponse::from(influencer)))
}
