use chrono::NaiveDateTime;
use serde::Serialize;

use super::entities::{InfluencerStatus, LastMessageInfo, MessageRole, MessageType};

#[derive(Debug, Serialize)]
pub struct InfluencerBasicInfo {
    pub id: String,
    pub name: String,
    pub display_name: String,
    pub avatar_url: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub suggested_messages: Option<Vec<String>>,
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
    pub created_at: NaiveDateTime,
}

#[derive(Debug, Serialize)]
pub struct ListInfluencersResponse {
    pub influencers: Vec<InfluencerResponse>,
    pub total: i64,
    pub limit: i64,
    pub offset: i64,
}

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
