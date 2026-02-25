use std::sync::LazyLock;

use regex::Regex;
use serde::Deserialize;
use utoipa::{IntoParams, ToSchema};
use validator::Validate;

use super::entities::MessageType;

static NAME_REGEX: LazyLock<Regex> = LazyLock::new(|| Regex::new(r"^[a-zA-Z0-9]+$").unwrap());

#[derive(Debug, Deserialize, Validate, ToSchema)]
pub struct CreateConversationRequest {
    #[validate(length(min = 1, message = "influencer_id is required"))]
    pub influencer_id: String,
}

#[derive(Debug, Deserialize, Validate, ToSchema)]
pub struct SendMessageRequest {
    pub message_type: String,

    #[validate(length(max = 4000, message = "content exceeds 4000 characters"))]
    #[schema(default = "")]
    pub content: Option<String>,

    pub media_urls: Option<Vec<String>>,

    pub audio_url: Option<String>,

    #[validate(range(min = 0, max = 300, message = "audio duration must be 0-300 seconds"))]
    pub audio_duration_seconds: Option<i32>,

    pub client_message_id: Option<String>,
}

impl SendMessageRequest {
    pub fn parsed_message_type(&self) -> Option<MessageType> {
        self.message_type.parse().ok()
    }

    pub fn validate_content(&self) -> Result<(), String> {
        let msg_type = self.parsed_message_type().ok_or("Invalid message type")?;
        let content = self.content.as_deref().unwrap_or("").trim();
        let media_urls = self.media_urls.as_deref().unwrap_or(&[]);

        match msg_type {
            MessageType::Text => {
                if content.is_empty() {
                    return Err("content is required for text messages".into());
                }
            }
            MessageType::Image => {
                if media_urls.is_empty() {
                    return Err("media_urls is required for image messages".into());
                }
                if media_urls.len() > 10 {
                    return Err("Too many media URLs (max 10)".into());
                }
            }
            MessageType::Multimodal => {
                if media_urls.is_empty() {
                    return Err("media_urls is required for multimodal messages".into());
                }
                if media_urls.len() > 10 {
                    return Err("Too many media URLs (max 10)".into());
                }
            }
            MessageType::Audio => {
                if self.audio_url.is_none() {
                    return Err("audio_url is required for audio messages".into());
                }
            }
        }

        Ok(())
    }
}

#[derive(Debug, Deserialize, IntoParams, ToSchema)]
pub struct PaginationParams {
    #[param(default = 50)]
    pub limit: Option<i64>,
    #[param(default = 0)]
    pub offset: Option<i64>,
}

impl PaginationParams {
    pub fn limit(&self, default: i64, max: i64) -> i64 {
        self.limit.unwrap_or(default).clamp(1, max)
    }
    pub fn offset(&self) -> i64 {
        self.offset.unwrap_or(0).max(0)
    }
}

#[derive(Debug, Deserialize, IntoParams, ToSchema)]
pub struct ListConversationsParams {
    #[param(default = 20)]
    pub limit: Option<i64>,
    #[param(default = 0)]
    pub offset: Option<i64>,
    pub influencer_id: Option<String>,
}

impl ListConversationsParams {
    pub fn limit(&self) -> i64 {
        self.limit.unwrap_or(20).clamp(1, 100)
    }
    pub fn offset(&self) -> i64 {
        self.offset.unwrap_or(0).max(0)
    }
}

#[derive(Debug, Deserialize, IntoParams, ToSchema)]
pub struct ListMessagesParams {
    #[param(default = 50)]
    pub limit: Option<i64>,
    #[param(default = 0)]
    pub offset: Option<i64>,
    #[param(default = "desc")]
    pub order: Option<String>,
}

impl ListMessagesParams {
    pub fn limit(&self) -> i64 {
        self.limit.unwrap_or(50).clamp(1, 200)
    }
    pub fn offset(&self) -> i64 {
        self.offset.unwrap_or(0).max(0)
    }
    pub fn order(&self) -> &str {
        match self.order.as_deref() {
            Some("asc") => "asc",
            _ => "desc",
        }
    }
}

#[derive(Debug, Deserialize, Validate, ToSchema)]
pub struct GeneratePromptRequest {
    #[validate(length(min = 1, max = 1000, message = "prompt must be 1-1000 characters"))]
    pub prompt: String,
}

#[derive(Debug, Deserialize, ToSchema)]
pub struct ValidateMetadataRequest {
    pub system_instructions: String,
}

#[derive(Debug, Deserialize, Validate, ToSchema)]
pub struct CreateInfluencerRequest {
    #[validate(length(min = 3, max = 15, message = "name must be 3-15 characters"))]
    #[validate(regex(path = *NAME_REGEX, message = "name must be alphanumeric"))]
    pub name: String,
    #[validate(length(min = 1, max = 100, message = "display_name must be 1-100 characters"))]
    pub display_name: String,
    #[validate(length(max = 500, message = "description max 500 characters"))]
    pub description: Option<String>,
    pub system_instructions: String,
    pub initial_greeting: Option<String>,
    #[serde(default)]
    pub suggested_messages: Vec<String>,
    #[serde(default = "default_personality_traits")]
    #[schema(value_type = Object)]
    pub personality_traits: serde_json::Value,
    pub category: Option<String>,
    pub avatar_url: Option<String>,
    pub bot_principal_id: String,
    #[allow(dead_code)]
    pub parent_principal_id: Option<String>,
    #[serde(default)]
    #[allow(dead_code)]
    pub is_nsfw: bool,
}

fn default_personality_traits() -> serde_json::Value {
    serde_json::json!({})
}

#[derive(Debug, Deserialize, ToSchema)]
pub struct GenerateImageRequest {
    #[serde(default)]
    pub prompt: Option<String>,
}

#[derive(Debug, Deserialize, ToSchema)]
pub struct UpdateSystemPromptRequest {
    pub system_instructions: String,
}

/// Multipart form body for media upload
#[derive(ToSchema)]
#[allow(dead_code)]
pub struct UploadMediaBody {
    /// The file to upload (image or audio)
    #[schema(format = Binary)]
    pub file: String,
    /// Media type: "image" or "audio"
    #[schema(rename = "type")]
    pub media_type: String,
}
