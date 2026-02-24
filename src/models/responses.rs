use chrono::NaiveDateTime;
use serde::Serialize;
use utoipa::ToSchema;

use super::entities::{InfluencerStatus, LastMessageInfo, MessageRole, MessageType};

#[derive(Debug, Serialize, ToSchema)]
pub struct InfluencerBasicInfo {
    pub id: String,
    pub name: String,
    pub display_name: String,
    pub avatar_url: Option<String>,
    pub is_online: bool,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub suggested_messages: Option<Vec<String>>,
}

#[derive(Debug, Serialize, ToSchema)]
pub struct InfluencerBasicInfoV2 {
    pub id: String,
    pub display_name: String,
    pub avatar_url: Option<String>,
    pub is_online: bool,
}

#[derive(Debug, Serialize, ToSchema)]
pub struct MessageResponse {
    pub id: String,
    pub role: MessageRole,
    pub content: Option<String>,
    pub message_type: MessageType,
    pub media_urls: Vec<String>,
    pub audio_url: Option<String>,
    pub audio_duration_seconds: Option<i32>,
    pub token_count: Option<i32>,
    pub created_at: NaiveDateTime,
    pub status: String,
    pub is_read: bool,
}

#[derive(Debug, Serialize, ToSchema)]
pub struct ConversationResponse {
    pub id: String,
    pub user_id: String,
    pub influencer: InfluencerBasicInfo,
    pub created_at: NaiveDateTime,
    pub updated_at: NaiveDateTime,
    pub message_count: i64,
    pub last_message: Option<LastMessageInfo>,
    pub recent_messages: Option<Vec<MessageResponse>>,
}

#[derive(Debug, Serialize, ToSchema)]
pub struct ConversationResponseV2 {
    pub id: String,
    pub user_id: String,
    pub influencer_id: String,
    pub influencer: InfluencerBasicInfoV2,
    pub created_at: NaiveDateTime,
    pub updated_at: NaiveDateTime,
    pub unread_count: i64,
    pub last_message: Option<LastMessageInfo>,
}

#[derive(Debug, Serialize, ToSchema)]
pub struct SendMessageResponse {
    pub user_message: MessageResponse,
    pub assistant_message: MessageResponse,
}

#[derive(Debug, Serialize, ToSchema)]
pub struct ListConversationsResponse {
    pub conversations: Vec<ConversationResponse>,
    pub total: i64,
    pub limit: i64,
    pub offset: i64,
}

#[derive(Debug, Serialize, ToSchema)]
pub struct ListConversationsResponseV2 {
    pub conversations: Vec<ConversationResponseV2>,
    pub total: i64,
    pub limit: i64,
    pub offset: i64,
}

#[derive(Debug, Serialize, ToSchema)]
pub struct ListMessagesResponse {
    pub conversation_id: String,
    pub messages: Vec<MessageResponse>,
    pub total: i64,
    pub limit: i64,
    pub offset: i64,
}

#[derive(Debug, Serialize, ToSchema)]
pub struct InfluencerResponse {
    pub id: String,
    pub name: String,
    pub display_name: String,
    pub avatar_url: Option<String>,
    pub description: Option<String>,
    pub category: Option<String>,
    pub is_active: InfluencerStatus,
    pub parent_principal_id: Option<String>,
    pub source: Option<String>,
    pub system_prompt: Option<String>,
    pub created_at: NaiveDateTime,
    pub conversation_count: Option<i64>,
    pub message_count: Option<i64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub starter_video_prompt: Option<String>,
}

#[derive(Debug, Serialize, ToSchema)]
pub struct ListInfluencersResponse {
    pub influencers: Vec<InfluencerResponse>,
    pub total: i64,
    pub limit: i64,
    pub offset: i64,
}

#[derive(Debug, Serialize, ToSchema)]
pub struct TrendingInfluencerResponse {
    pub id: String,
    pub name: String,
    pub display_name: String,
    pub avatar_url: Option<String>,
    pub description: Option<String>,
    pub category: Option<String>,
    pub is_active: InfluencerStatus,
    pub created_at: NaiveDateTime,
    pub conversation_count: i64,
    pub message_count: i64,
}

#[derive(Debug, Serialize, ToSchema)]
pub struct ListTrendingInfluencersResponse {
    pub influencers: Vec<TrendingInfluencerResponse>,
    pub total: i64,
    pub limit: i64,
    pub offset: i64,
}

#[derive(Debug, Serialize, ToSchema)]
pub struct SystemPromptResponse {
    pub system_instructions: String,
}

#[derive(Debug, Serialize, ToSchema)]
pub struct GeneratedMetadataResponse {
    pub is_valid: bool,
    pub reason: Option<String>,
    pub name: Option<String>,
    pub display_name: Option<String>,
    pub description: Option<String>,
    pub avatar_url: Option<String>,
    pub initial_greeting: Option<String>,
    pub suggested_messages: Option<Vec<String>>,
    #[schema(value_type = Option<Object>)]
    pub personality_traits: Option<serde_json::Value>,
    pub category: Option<String>,
}

#[derive(Debug, Serialize, ToSchema)]
pub struct MarkConversationAsReadResponse {
    pub id: String,
    pub unread_count: i64,
    pub last_read_at: NaiveDateTime,
}

// ── Health / Status ──

#[derive(Debug, Serialize, ToSchema)]
pub struct ServiceHealth {
    pub status: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub latency_ms: Option<i64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub error: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub pool_size: Option<u32>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub pool_free: Option<u32>,
}

#[derive(Debug, Serialize, ToSchema)]
pub struct HealthResponse {
    pub status: String,
    pub timestamp: NaiveDateTime,
    pub services: std::collections::HashMap<String, ServiceHealth>,
}

#[derive(Debug, Serialize, ToSchema)]
pub struct StatusResponse {
    pub service: String,
    pub version: String,
    pub environment: String,
    pub uptime_seconds: u64,
    pub database: DatabaseStats,
    pub statistics: SystemStatistics,
    pub timestamp: NaiveDateTime,
}

#[derive(Debug, Serialize, ToSchema)]
pub struct DatabaseStats {
    pub connected: bool,
    pub pool_size: Option<u32>,
    pub active_connections: Option<u32>,
}

#[derive(Debug, Serialize, ToSchema)]
pub struct SystemStatistics {
    pub total_conversations: i64,
    pub total_messages: i64,
    pub active_influencers: i64,
}

#[derive(Debug, Serialize, ToSchema)]
pub struct MediaUploadResponse {
    pub url: String,
    pub storage_key: String,
    #[serde(rename = "type")]
    pub media_type: String,
    pub size: u64,
    pub mime_type: String,
    pub duration_seconds: Option<i32>,
    pub uploaded_at: NaiveDateTime,
}

#[derive(Debug, Serialize, ToSchema)]
pub struct DeleteConversationResponse {
    pub success: bool,
    pub message: String,
    pub deleted_conversation_id: String,
    pub deleted_messages_count: i64,
}
