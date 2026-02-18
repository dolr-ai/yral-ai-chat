use chrono::NaiveDateTime;
use serde::Serialize;

use super::entities::{InfluencerStatus, LastMessageInfo, MessageRole, MessageType};

#[derive(Debug, Serialize)]
pub struct InfluencerBasicInfo {
    pub id: String,
    pub name: String,
    pub display_name: String,
    pub avatar_url: Option<String>,
    pub is_online: bool,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub suggested_messages: Option<Vec<String>>,
}

#[derive(Debug, Serialize)]
pub struct InfluencerBasicInfoV2 {
    pub id: String,
    pub display_name: String,
    pub avatar_url: Option<String>,
    pub is_online: bool,
}

#[derive(Debug, Serialize)]
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

#[derive(Debug, Serialize)]
pub struct ConversationResponse {
    pub id: String,
    pub user_id: String,
    pub influencer: InfluencerBasicInfo,
    pub created_at: NaiveDateTime,
    pub updated_at: NaiveDateTime,
    pub message_count: i64,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub last_message: Option<LastMessageInfo>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub recent_messages: Option<Vec<MessageResponse>>,
}

#[derive(Debug, Serialize)]
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

#[derive(Debug, Serialize)]
pub struct SendMessageResponse {
    pub user_message: MessageResponse,
    pub assistant_message: MessageResponse,
}

#[derive(Debug, Serialize)]
pub struct ListConversationsResponse {
    pub conversations: Vec<ConversationResponse>,
    pub total: i64,
    pub limit: i64,
    pub offset: i64,
}

#[derive(Debug, Serialize)]
pub struct ListConversationsResponseV2 {
    pub conversations: Vec<ConversationResponseV2>,
    pub total: i64,
    pub limit: i64,
    pub offset: i64,
}

#[derive(Debug, Serialize)]
pub struct ListMessagesResponse {
    pub conversation_id: String,
    pub messages: Vec<MessageResponse>,
    pub total: i64,
    pub limit: i64,
    pub offset: i64,
}

#[derive(Debug, Serialize)]
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
    #[serde(skip_serializing_if = "Option::is_none")]
    pub system_prompt: Option<String>,
    pub created_at: NaiveDateTime,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub conversation_count: Option<i64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub message_count: Option<i64>,
}

#[derive(Debug, Serialize)]
pub struct InfluencerCreateResponse {
    pub id: String,
    pub name: String,
    pub display_name: String,
    pub avatar_url: Option<String>,
    pub description: Option<String>,
    pub category: Option<String>,
    pub is_active: InfluencerStatus,
    pub parent_principal_id: Option<String>,
    pub source: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub system_prompt: Option<String>,
    pub created_at: NaiveDateTime,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub starter_video_prompt: Option<String>,
}

#[derive(Debug, Serialize)]
pub struct ListInfluencersResponse {
    pub influencers: Vec<InfluencerResponse>,
    pub total: i64,
    pub limit: i64,
    pub offset: i64,
}

#[derive(Debug, Serialize)]
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

#[derive(Debug, Serialize)]
pub struct ListTrendingInfluencersResponse {
    pub influencers: Vec<TrendingInfluencerResponse>,
    pub total: i64,
    pub limit: i64,
    pub offset: i64,
}

#[derive(Debug, Serialize)]
pub struct SystemPromptResponse {
    pub system_instructions: String,
}

#[derive(Debug, Serialize)]
pub struct GeneratedMetadataResponse {
    pub is_valid: bool,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub reason: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub name: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub display_name: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub description: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub avatar_url: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub initial_greeting: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub suggested_messages: Option<Vec<String>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub personality_traits: Option<serde_json::Value>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub category: Option<String>,
}

#[derive(Debug, Serialize)]
pub struct MarkConversationAsReadResponse {
    pub id: String,
    pub unread_count: i64,
    pub last_read_at: NaiveDateTime,
}

#[derive(Debug, Serialize)]
pub struct GenerateImageResponse {
    pub image_url: Option<String>,
    pub prompt_used: String,
}

// ── Health / Status ──

#[derive(Debug, Serialize)]
pub struct ServiceHealth {
    pub status: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub latency_ms: Option<i64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub error: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub pool_size: Option<u32>,
}

#[derive(Debug, Serialize)]
pub struct HealthResponse {
    pub status: String,
    pub timestamp: NaiveDateTime,
    pub services: std::collections::HashMap<String, ServiceHealth>,
}

#[derive(Debug, Serialize)]
pub struct StatusResponse {
    pub service: String,
    pub version: String,
    pub environment: String,
    pub uptime_seconds: u64,
    pub database: DatabaseStats,
    pub statistics: SystemStatistics,
    pub timestamp: NaiveDateTime,
}

#[derive(Debug, Serialize)]
pub struct DatabaseStats {
    pub connected: bool,
    pub pool_size: Option<u32>,
}

#[derive(Debug, Serialize)]
pub struct SystemStatistics {
    pub total_conversations: i64,
    pub total_messages: i64,
    pub active_influencers: i64,
}

#[derive(Debug, Serialize)]
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

#[derive(Debug, Serialize)]
pub struct DeleteConversationResponse {
    pub success: bool,
    pub message: String,
    pub deleted_conversation_id: String,
    pub deleted_messages_count: i64,
}

#[derive(Debug, Serialize)]
pub struct ErrorResponse {
    pub error: String,
    pub message: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub details: Option<serde_json::Value>,
}
