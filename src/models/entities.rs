use chrono::NaiveDateTime;
use serde::{Deserialize, Serialize};
use strum::{AsRefStr, Display, EnumString};
use utoipa::ToSchema;

// ── Enums ──

#[derive(
    Debug,
    Clone,
    Serialize,
    Deserialize,
    PartialEq,
    sqlx::Type,
    Display,
    EnumString,
    AsRefStr,
    ToSchema,
)]
#[sqlx(rename_all = "lowercase")]
#[strum(serialize_all = "lowercase", ascii_case_insensitive)]
pub enum MessageType {
    #[serde(rename = "text")]
    Text,
    #[serde(rename = "multimodal")]
    Multimodal,
    #[serde(rename = "image")]
    Image,
    #[serde(rename = "audio")]
    Audio,
}

#[derive(
    Debug,
    Clone,
    Serialize,
    Deserialize,
    PartialEq,
    sqlx::Type,
    Display,
    EnumString,
    AsRefStr,
    ToSchema,
)]
#[sqlx(rename_all = "lowercase")]
#[strum(serialize_all = "lowercase", ascii_case_insensitive)]
pub enum MessageRole {
    #[serde(rename = "user")]
    User,
    #[serde(rename = "assistant")]
    Assistant,
}

#[derive(
    Debug, Clone, Serialize, Deserialize, PartialEq, Display, EnumString, AsRefStr, ToSchema,
)]
#[strum(serialize_all = "snake_case")]
pub enum InfluencerStatus {
    #[serde(rename = "active")]
    Active,
    #[serde(rename = "coming_soon")]
    ComingSoon,
    #[serde(rename = "discontinued")]
    Discontinued,
}

// ── Entities ──

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AIInfluencer {
    pub id: String,
    pub name: String,
    pub display_name: String,
    pub avatar_url: Option<String>,
    pub description: Option<String>,
    pub category: Option<String>,
    pub system_instructions: String,
    pub personality_traits: serde_json::Value,
    pub initial_greeting: Option<String>,
    pub suggested_messages: Vec<String>,
    pub is_active: InfluencerStatus,
    pub is_nsfw: bool,
    pub parent_principal_id: Option<String>,
    pub source: Option<String>,
    pub created_at: NaiveDateTime,
    pub updated_at: NaiveDateTime,
    pub metadata: serde_json::Value,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub conversation_count: Option<i64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub message_count: Option<i64>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Conversation {
    pub id: String,
    pub user_id: String,
    pub influencer_id: String,
    pub created_at: NaiveDateTime,
    pub updated_at: NaiveDateTime,
    pub metadata: serde_json::Value,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub influencer: Option<AIInfluencer>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub message_count: Option<i64>,
    pub unread_count: i64,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub last_message: Option<LastMessageInfo>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub recent_messages: Option<Vec<Message>>,
}

#[derive(Debug, Clone, Serialize, Deserialize, ToSchema)]
pub struct LastMessageInfo {
    pub content: Option<String>,
    pub role: MessageRole,
    pub created_at: NaiveDateTime,
    #[schema(default = "delivered")]
    pub status: Option<String>,
    pub is_read: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Message {
    pub id: String,
    pub conversation_id: String,
    pub role: MessageRole,
    pub content: Option<String>,
    pub message_type: MessageType,
    pub media_urls: Vec<String>,
    pub audio_url: Option<String>,
    pub audio_duration_seconds: Option<i32>,
    pub token_count: Option<i32>,
    pub client_message_id: Option<String>,
    pub created_at: NaiveDateTime,
    pub metadata: serde_json::Value,
    pub status: String,
    pub is_read: bool,
}
