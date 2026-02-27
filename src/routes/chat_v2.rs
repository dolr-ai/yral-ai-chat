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
                yral_canisters_client::user_info_service::UserAccountType::BotAccount { .. } => {
                    CallerType::Bot
                }
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

/// Batch fetch user profile pictures from the User Info Service canister.
/// Returns a map of principal_id -> UserBasicInfo.
async fn batch_fetch_user_profiles(
    agent: &ic_agent::Agent,
    user_ids: &[String],
) -> HashMap<String, UserBasicInfo> {
    let mut profiles = HashMap::new();

    // Pre-fill with defaults
    for uid in user_ids {
        profiles.insert(
            uid.clone(),
            UserBasicInfo {
                principal_id: uid.clone(),
                profile_picture_url: None,
            },
        );
    }

    if user_ids.is_empty() {
        return profiles;
    }

    // Parse principals
    let principals: Vec<candid::Principal> = user_ids
        .iter()
        .filter_map(|id| candid::Principal::from_text(id).ok())
        .collect();

    if principals.is_empty() {
        return profiles;
    }

    let canister_id = yral_canisters_client::ic::USER_INFO_SERVICE_ID;
    let service = yral_canisters_client::user_info_service::UserInfoService(canister_id, agent);

    match service.get_users_profile_details(principals).await {
        Ok(yral_canisters_client::user_info_service::Result9::Ok(details)) => {
            for detail in details {
                let pid = detail.principal_id.to_text();
                let pic_url = detail.profile_picture.map(|p| p.url);
                profiles.insert(
                    pid.clone(),
                    UserBasicInfo {
                        principal_id: pid,
                        profile_picture_url: pic_url,
                    },
                );
            }
        }
        Ok(yral_canisters_client::user_info_service::Result9::Err(e)) => {
            tracing::warn!(error = %e, "Canister error fetching user profiles");
        }
        Err(e) => {
            tracing::warn!(error = %e, "IC agent error fetching user profiles");
        }
    }

    profiles
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
            list_for_bot(conv_repo, &state.ic_agent, &user.user_id, limit, offset).await
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

    let user_profiles = batch_fetch_user_profiles(agent, &unique_user_ids).await;

    let conversations = conversations
        .into_iter()
        .map(|conv| {
            let user_info = user_profiles
                .get(&conv.user_id)
                .cloned()
                .unwrap_or_else(|| UserBasicInfo {
                    principal_id: conv.user_id.clone(),
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
