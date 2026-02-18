use serde::Deserialize;
use validator::Validate;

use super::entities::MessageType;

#[derive(Debug, Deserialize, Validate)]
pub struct CreateConversationRequest {
    #[validate(length(min = 1, message = "influencer_id is required"))]
    pub influencer_id: String,
}

#[derive(Debug, Deserialize, Validate)]
pub struct SendMessageRequest {
    pub message_type: String,

    #[validate(length(max = 4000, message = "content exceeds 4000 characters"))]
    pub content: Option<String>,

    pub media_urls: Option<Vec<String>>,

    pub audio_url: Option<String>,

    #[validate(range(min = 0, max = 300, message = "audio duration must be 0-300 seconds"))]
    pub audio_duration_seconds: Option<i32>,

    pub client_message_id: Option<String>,
}

impl SendMessageRequest {
    pub fn parsed_message_type(&self) -> Option<MessageType> {
        MessageType::from_str(&self.message_type)
    }

    pub fn validate_content(&self) -> Result<(), String> {
        let msg_type = self
            .parsed_message_type()
            .ok_or("Invalid message type")?;
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

#[derive(Debug, Deserialize)]
pub struct PaginationParams {
    pub limit: Option<i64>,
    pub offset: Option<i64>,
}

impl PaginationParams {
    pub fn limit(&self) -> i64 {
        self.limit.unwrap_or(50).clamp(1, 100)
    }

    pub fn offset(&self) -> i64 {
        self.offset.unwrap_or(0).max(0)
    }
}

#[derive(Debug, Deserialize)]
pub struct ListConversationsParams {
    pub limit: Option<i64>,
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

#[derive(Debug, Deserialize)]
pub struct ListMessagesParams {
    pub limit: Option<i64>,
    pub offset: Option<i64>,
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
