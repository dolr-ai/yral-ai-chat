use std::sync::Arc;

use axum::Json;
use axum::extract::{Query, State};

use crate::AppState;
use crate::db::repositories::ConversationRepository;
use crate::error::AppError;
use crate::middleware::AuthenticatedUser;
use crate::models::entities::InfluencerStatus;
use crate::models::requests::ListConversationsParams;
use crate::models::responses::{
    ConversationResponseV2, InfluencerBasicInfoV2, ListConversationsResponseV2,
};

// GET /api/v2/chat/conversations
pub async fn list_conversations_v2(
    State(state): State<Arc<AppState>>,
    user: AuthenticatedUser,
    Query(params): Query<ListConversationsParams>,
) -> Result<Json<ListConversationsResponseV2>, AppError> {
    let conv_repo = ConversationRepository::new(state.db.pool.clone());

    let limit = params.limit();
    let offset = params.offset();
    let influencer_id = params.influencer_id.as_deref();

    let (conversations, total) = tokio::try_join!(
        conv_repo.list_by_user(&user.user_id, influencer_id, limit, offset),
        conv_repo.count_by_user(&user.user_id, influencer_id),
    )?;

    let conversations = conversations
        .into_iter()
        .map(|conv| {
            let influencer_info = conv
                .influencer
                .as_ref()
                .map(|i| InfluencerBasicInfoV2 {
                    id: i.id.clone(),
                    display_name: i.display_name.clone(),
                    avatar_url: i.avatar_url.clone(),
                    is_online: i.is_active == InfluencerStatus::Active,
                })
                .unwrap_or_else(|| InfluencerBasicInfoV2 {
                    id: conv.influencer_id.clone(),
                    display_name: String::new(),
                    avatar_url: None,
                    is_online: false,
                });

            ConversationResponseV2 {
                id: conv.id,
                user_id: conv.user_id,
                influencer_id: conv.influencer_id,
                influencer: influencer_info,
                created_at: conv.created_at,
                updated_at: conv.updated_at,
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
