use chrono::NaiveDateTime;
use serde::{Deserialize, Serialize};

// ── Enums ──

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, sqlx::Type)]
#[sqlx(rename_all = "lowercase")]
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

impl MessageType {
    pub fn as_str(&self) -> &str {
        match self {
            Self::Text => "text",
            Self::Multimodal => "multimodal",
            Self::Image => "image",
            Self::Audio => "audio",
        }
    }

    pub fn from_str(s: &str) -> Option<Self> {
        match s.to_lowercase().as_str() {
            "text" => Some(Self::Text),
            "multimodal" => Some(Self::Multimodal),
            "image" => Some(Self::Image),
            "audio" => Some(Self::Audio),
            _ => None,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, sqlx::Type)]
#[sqlx(rename_all = "lowercase")]
pub enum MessageRole {
    #[serde(rename = "user")]
    User,
    #[serde(rename = "assistant")]
    Assistant,
}

impl MessageRole {
    pub fn as_str(&self) -> &str {
        match self {
            Self::User => "user",
            Self::Assistant => "assistant",
        }
    }

    pub fn from_str(s: &str) -> Option<Self> {
        match s.to_lowercase().as_str() {
            "user" => Some(Self::User),
            "assistant" => Some(Self::Assistant),
            _ => None,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub enum InfluencerStatus {
    #[serde(rename = "active")]
    Active,
    #[serde(rename = "coming_soon")]
    ComingSoon,
    #[serde(rename = "discontinued")]
    Discontinued,
}

impl InfluencerStatus {
    pub fn as_str(&self) -> &str {
        match self {
            Self::Active => "active",
            Self::ComingSoon => "coming_soon",
            Self::Discontinued => "discontinued",
        }
    }

    pub fn from_str(s: &str) -> Self {
        match s {
            "active" => Self::Active,
            "coming_soon" => Self::ComingSoon,
            "discontinued" => Self::Discontinued,
            _ => Self::Active,
        }
    }
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

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LastMessageInfo {
    pub content: Option<String>,
    pub role: MessageRole,
    pub created_at: NaiveDateTime,
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
