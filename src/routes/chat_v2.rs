use std::collections::HashMap;
use std::sync::Arc;

use axum::Json;
use axum::extract::{Query, State};

use crate::AppState;
use crate::db::repositories::ConversationRepository;
use crate::error::{AppError, ErrorBody};
use crate::middleware::AuthenticatedUser;
use crate::models::entities::InfluencerStatus;
use crate::models::requests::ListConversationsParams;
use crate::models::responses::{
    ConversationResponseV2, InfluencerBasicInfoV2, ListConversationsResponseV2, UserBasicInfo,
};

/// Whether the authenticated caller is a regular user or a bot.
enum CallerType {
    User,
    Bot,
}

/// Determine if the caller is a bot or user by querying the User Info Service canister.
/// Falls back to `User` on any error (parsing, network, canister error).
async fn resolve_caller_type(agent: &ic_agent::Agent, principal_str: &str) -> CallerType {
    let principal = match candid::Principal::from_text(principal_str) {
        Ok(p) => p,
        Err(e) => {
            tracing::debug!(error = %e, principal = %principal_str, "Failed to parse principal, defaulting to User");
            return CallerType::User;
        }
    };

    let canister_id = yral_canisters_client::ic::USER_INFO_SERVICE_ID;
    let service = yral_canisters_client::user_info_service::UserInfoService(canister_id, agent);

    match service.get_user_profile_details_v_7(principal).await {
        Ok(yral_canisters_client::user_info_service::Result7::Ok(profile)) => {
            match profile.account_type {
                yral_canisters_client::user_info_service::UserAccountType::BotAccount {
                    ..
                } => CallerType::Bot,
                yral_canisters_client::user_info_service::UserAccountType::MainAccount {
                    ..
                } => CallerType::User,
            }
        }
        Ok(yral_canisters_client::user_info_service::Result7::Err(e)) => {
            tracing::warn!(error = %e, "Canister returned error for caller type lookup, defaulting to User");
            CallerType::User
        }
        Err(e) => {
            tracing::warn!(error = %e, "IC agent error during caller type lookup, defaulting to User");
            CallerType::User
        }
    }
}

/// Batch fetch user profiles: profile pictures from canister + usernames from metadata server.
/// Returns a map of principal_id -> UserBasicInfo.
async fn batch_fetch_user_profiles(
    agent: &ic_agent::Agent,
    http_client: &reqwest::Client,
    metadata_url: &str,
    user_ids: &[String],
) -> HashMap<String, UserBasicInfo> {
    let mut profiles: HashMap<String, UserBasicInfo> = user_ids
        .iter()
        .map(|uid| {
            (
                uid.clone(),
                UserBasicInfo {
                    principal_id: uid.clone(),
                    username: None,
                    profile_picture_url: None,
                },
            )
        })
        .collect();

    if user_ids.is_empty() {
        return profiles;
    }

    // Fetch usernames from metadata server and profile pics from canister in parallel
    let (metadata_result, canister_result) = tokio::join!(
        fetch_usernames_from_metadata(http_client, metadata_url, user_ids),
        fetch_profile_pics_from_canister(agent, user_ids),
    );

    // Merge metadata (usernames)
    for (pid, username) in metadata_result {
        if let Some(info) = profiles.get_mut(&pid) {
            info.username = Some(username);
        }
    }

    // Merge canister data (profile pictures)
    for (pid, pic_url) in canister_result {
        if let Some(info) = profiles.get_mut(&pid) {
            info.profile_picture_url = Some(pic_url);
        }
    }

    profiles
}

/// Fetch usernames from the yral metadata server via POST /metadata-bulk.
async fn fetch_usernames_from_metadata(
    http_client: &reqwest::Client,
    metadata_url: &str,
    user_ids: &[String],
) -> HashMap<String, String> {
    let url = format!("{}/metadata-bulk", metadata_url.trim_end_matches('/'));

    let body = serde_json::json!({ "users": user_ids });

    let result: HashMap<String, String> = match http_client
        .post(&url)
        .json(&body)
        .send()
        .await
    {
        Ok(resp) => {
            if !resp.status().is_success() {
                tracing::warn!(status = %resp.status(), "Metadata server returned error for bulk fetch");
                return HashMap::new();
            }
            match resp.json::<serde_json::Value>().await {
                Ok(json) => {
                    let mut usernames = HashMap::new();
                    if let Some(ok_data) = json.get("ok").and_then(|v| v.as_object()) {
                        for (principal, meta) in ok_data {
                            if let Some(name) = meta.get("user_name").and_then(|v| v.as_str()) {
                                if !name.trim().is_empty() {
                                    usernames.insert(principal.clone(), name.to_string());
                                }
                            }
                        }
                    }
                    usernames
                }
                Err(e) => {
                    tracing::warn!(error = %e, "Failed to parse metadata bulk response");
                    HashMap::new()
                }
            }
        }
        Err(e) => {
            tracing::warn!(error = %e, "Failed to fetch usernames from metadata server");
            HashMap::new()
        }
    };

    result
}

/// Fetch profile pictures from the User Info Service canister.
async fn fetch_profile_pics_from_canister(
    agent: &ic_agent::Agent,
    user_ids: &[String],
) -> HashMap<String, String> {
    let principals: Vec<candid::Principal> = user_ids
        .iter()
        .filter_map(|id| candid::Principal::from_text(id).ok())
        .collect();

    if principals.is_empty() {
        return HashMap::new();
    }

    let canister_id = yral_canisters_client::ic::USER_INFO_SERVICE_ID;
    let service = yral_canisters_client::user_info_service::UserInfoService(canister_id, agent);

    match service.get_users_profile_details(principals).await {
        Ok(yral_canisters_client::user_info_service::Result9::Ok(details)) => {
            let mut pics = HashMap::new();
            for detail in details {
                if let Some(pic) = detail.profile_picture {
                    pics.insert(detail.principal_id.to_text(), pic.url);
                }
            }
            pics
        }
        Ok(yral_canisters_client::user_info_service::Result9::Err(e)) => {
            tracing::warn!(error = %e, "Canister error fetching user profiles");
            HashMap::new()
        }
        Err(e) => {
            tracing::warn!(error = %e, "IC agent error fetching user profiles");
            HashMap::new()
        }
    }
}

/// List user's conversations (V2 with enriched influencer info)
#[utoipa::path(
    get,
    path = "/api/v2/chat/conversations",
    params(ListConversationsParams),
    responses(
        (status = 200, body = ListConversationsResponseV2, description = "Successful response"),
        (status = 401, body = ErrorBody, description = "Unauthorized"),
        (status = 422, body = ErrorBody, description = "Validation error")
    ),
    tag = "Chat V2",
    security(("BearerAuth" = []))
)]
pub async fn list_conversations_v2(
    State(state): State<Arc<AppState>>,
    user: AuthenticatedUser,
    Query(params): Query<ListConversationsParams>,
) -> Result<Json<ListConversationsResponseV2>, AppError> {
    let conv_repo = ConversationRepository::new(state.db.pool.clone());
    let limit = params.limit();
    let offset = params.offset();

    // Determine if the caller is a bot or user via canister lookup
    let caller_type = resolve_caller_type(&state.ic_agent, &user.user_id).await;

    match caller_type {
        CallerType::User => list_for_user(conv_repo, &user.user_id, &params, limit, offset).await,
        CallerType::Bot => {
            list_for_bot(
                conv_repo,
                &state.ic_agent,
                &state.http_client,
                &state.settings.metadata_url,
                &user.user_id,
                limit,
                offset,
            )
            .await
        }
    }
}

/// User is fetching conversations → return influencer info as the peer.
async fn list_for_user(
    conv_repo: ConversationRepository,
    user_id: &str,
    params: &ListConversationsParams,
    limit: i64,
    offset: i64,
) -> Result<Json<ListConversationsResponseV2>, AppError> {
    let influencer_id = params.influencer_id.as_deref();

    let (conversations, total) = tokio::try_join!(
        conv_repo.list_by_user(user_id, influencer_id, limit, offset),
        conv_repo.count_by_user(user_id, influencer_id),
    )?;

    let conversations = conversations
        .into_iter()
        .map(|conv| {
            let influencer_info = conv
                .influencer
                .as_ref()
                .map(|i| InfluencerBasicInfoV2 {
                    id: i.id.clone(),
                    name: i.name.clone(),
                    display_name: i.display_name.clone(),
                    avatar_url: i.avatar_url.clone(),
                    is_online: i.is_active == InfluencerStatus::Active,
                })
                .unwrap_or_else(|| InfluencerBasicInfoV2 {
                    id: conv.influencer_id.clone(),
                    name: String::new(),
                    display_name: String::new(),
                    avatar_url: None,
                    is_online: false,
                });

            ConversationResponseV2 {
                id: conv.id,
                user_id: conv.user_id,
                influencer_id: conv.influencer_id,
                influencer: Some(influencer_info),
                user: None,
                created_at: conv.created_at,
                updated_at: conv.updated_at,
                message_count: conv.message_count.unwrap_or(0),
                unread_count: conv.unread_count,
                last_message: conv.last_message,
            }
        })
        .collect();

    Ok(Json(ListConversationsResponseV2 {
        conversations,
        total,
        limit,
        offset,
    }))
}

/// Bot is fetching conversations → return user info as the peer.
/// The bot's principal (user_id from JWT) IS the influencer_id in the DB.
async fn list_for_bot(
    conv_repo: ConversationRepository,
    agent: &ic_agent::Agent,
    http_client: &reqwest::Client,
    metadata_url: &str,
    bot_principal: &str,
    limit: i64,
    offset: i64,
) -> Result<Json<ListConversationsResponseV2>, AppError> {
    let (conversations, total) = tokio::try_join!(
        conv_repo.list_by_influencer(bot_principal, limit, offset),
        conv_repo.count_by_influencer(bot_principal),
    )?;

    // Collect unique user principals for batch profile fetch
    let unique_user_ids: Vec<String> = conversations
        .iter()
        .map(|c| c.user_id.clone())
        .collect::<std::collections::HashSet<_>>()
        .into_iter()
        .collect();

    let user_profiles =
        batch_fetch_user_profiles(agent, http_client, metadata_url, &unique_user_ids).await;

    let conversations = conversations
        .into_iter()
        .map(|conv| {
            let user_info = user_profiles
                .get(&conv.user_id)
                .cloned()
                .unwrap_or_else(|| UserBasicInfo {
                    principal_id: conv.user_id.clone(),
                    username: None,
                    profile_picture_url: None,
                });

            ConversationResponseV2 {
                id: conv.id,
                user_id: conv.user_id,
                influencer_id: conv.influencer_id,
                influencer: None,
                user: Some(user_info),
                created_at: conv.created_at,
                updated_at: conv.updated_at,
                message_count: conv.message_count.unwrap_or(0),
                unread_count: conv.unread_count,
                last_message: conv.last_message,
            }
        })
        .collect();

    Ok(Json(ListConversationsResponseV2 {
        conversations,
        total,
        limit,
        offset,
    }))
}
