use std::collections::HashMap;

use async_openai::config::OpenAIConfig;
use async_openai::types::chat::{
    ChatCompletionRequestAssistantMessage, ChatCompletionRequestMessage,
    ChatCompletionRequestMessageContentPartImage,
    ChatCompletionRequestMessageContentPartText, ChatCompletionRequestSystemMessage,
    ChatCompletionRequestUserMessage, ChatCompletionRequestUserMessageContent,
    ChatCompletionRequestUserMessageContentPart, CreateChatCompletionRequestArgs, ImageUrl,
};
use async_openai::Client;
use base64::Engine;
use serde::Deserialize;

use crate::error::AppError;
use crate::models::entities::{Message, MessageRole};

#[derive(Clone)]
pub struct AiClient {
    client: Client<OpenAIConfig>,
    model: String,
    max_tokens: u32,
    temperature: f32,
    configured: bool,
    // For Gemini transcription (native API, not OpenAI-compatible)
    gemini_api_key: Option<String>,
    gemini_model: Option<String>,
    raw_http: reqwest::Client,
}

impl AiClient {
    pub fn gemini(
        http: reqwest::Client,
        api_key: &str,
        model: &str,
        max_tokens: u32,
        temperature: f32,
        _timeout: u64,
    ) -> Self {
        let config = OpenAIConfig::new()
            .with_api_key(api_key)
            .with_api_base("https://generativelanguage.googleapis.com/v1beta/openai");

        let client = Client::with_config(config).with_http_client(http.clone());

        Self {
            client,
            model: model.to_string(),
            max_tokens,
            temperature,
            configured: !api_key.is_empty(),
            gemini_api_key: Some(api_key.to_string()),
            gemini_model: Some(model.to_string()),
            raw_http: http,
        }
    }

    pub fn openrouter(
        http: reqwest::Client,
        api_key: &str,
        model: &str,
        max_tokens: u32,
        temperature: f32,
        _timeout: u64,
    ) -> Self {
        let config = OpenAIConfig::new()
            .with_api_key(api_key)
            .with_api_base("https://openrouter.ai/api/v1");

        let mut headers = reqwest::header::HeaderMap::new();
        headers.insert("HTTP-Referer", "https://yral.com".parse().unwrap());
        headers.insert("X-Title", "Yral AI Chat".parse().unwrap());
        let custom_http = reqwest::ClientBuilder::new()
            .default_headers(headers)
            .build()
            .unwrap_or(http.clone());

        let client = Client::with_config(config).with_http_client(custom_http);

        Self {
            client,
            model: model.to_string(),
            max_tokens,
            temperature,
            configured: !api_key.is_empty(),
            gemini_api_key: None,
            gemini_model: None,
            raw_http: http,
        }
    }

    pub fn is_configured(&self) -> bool {
        self.configured
    }

    pub async fn generate_response(
        &self,
        user_message: &str,
        system_instructions: &str,
        conversation_history: &[Message],
        media_urls: Option<&[String]>,
    ) -> Result<(String, i32), AppError> {
        let mut messages: Vec<ChatCompletionRequestMessage> = Vec::new();

        // System message
        messages.push(ChatCompletionRequestMessage::System(
            ChatCompletionRequestSystemMessage {
                content: system_instructions.into(),
                name: None,
            },
        ));

        // Conversation history
        for msg in conversation_history {
            match msg.role {
                MessageRole::User => {
                    let content = build_user_content(
                        msg.content.as_deref().unwrap_or(""),
                        &msg.media_urls,
                    );
                    messages.push(ChatCompletionRequestMessage::User(
                        ChatCompletionRequestUserMessage {
                            content,
                            name: None,
                        },
                    ));
                }
                MessageRole::Assistant => {
                    messages.push(ChatCompletionRequestMessage::Assistant(
                        ChatCompletionRequestAssistantMessage {
                            content: msg.content.clone().map(Into::into),
                            name: None,
                            ..Default::default()
                        },
                    ));
                }
            }
        }

        // Current user message
        let current_content = build_user_content(
            user_message,
            media_urls.unwrap_or(&[]),
        );
        messages.push(ChatCompletionRequestMessage::User(
            ChatCompletionRequestUserMessage {
                content: current_content,
                name: None,
            },
        ));

        let request = CreateChatCompletionRequestArgs::default()
            .model(&self.model)
            .messages(messages)
            .temperature(self.temperature)
            .max_tokens(self.max_tokens)
            .build()
            .map_err(|e| AppError::service_unavailable(format!("Failed to build request: {e}")))?;

        let response = self
            .client
            .chat()
            .create(request)
            .await
            .map_err(|e| AppError::service_unavailable(format!("AI API error: {e}")))?;

        let choice = response
            .choices
            .first()
            .ok_or_else(|| AppError::service_unavailable("Empty response from AI"))?;

        let text = choice
            .message
            .content
            .clone()
            .unwrap_or_default();

        let token_count = response
            .usage
            .map(|u| u.total_tokens as i32)
            .unwrap_or_else(|| estimate_tokens(&text));

        Ok((text, token_count))
    }

    /// Transcribe audio using Gemini's native API (not OpenAI-compatible).
    /// Only works on AiClient instances created with `AiClient::gemini()`.
    pub async fn transcribe_audio(&self, audio_url: &str) -> Result<String, AppError> {
        let api_key = self
            .gemini_api_key
            .as_deref()
            .ok_or_else(|| AppError::service_unavailable("Transcription requires Gemini client"))?;
        let model = self.gemini_model.as_deref().unwrap_or("gemini-2.5-flash");

        // Download audio
        let resp = self
            .raw_http
            .get(audio_url)
            .timeout(std::time::Duration::from_secs(15))
            .send()
            .await
            .map_err(|e| AppError::service_unavailable(format!("Failed to download audio: {e}")))?;

        let content_type = resp
            .headers()
            .get("content-type")
            .and_then(|v| v.to_str().ok())
            .unwrap_or("audio/mpeg")
            .to_string();

        let bytes = resp
            .bytes()
            .await
            .map_err(|e| AppError::service_unavailable(format!("Failed to read audio: {e}")))?;

        let b64 = base64::engine::general_purpose::STANDARD.encode(&bytes);

        // Call native Gemini API for transcription
        let request_body = serde_json::json!({
            "contents": [{
                "parts": [
                    {"text": "Please transcribe this audio file accurately. Only return the transcription text without any additional commentary."},
                    {"inlineData": {"mimeType": content_type, "data": b64}}
                ]
            }],
            "generationConfig": {"temperature": 0.1, "maxOutputTokens": 4096}
        });

        let url = format!(
            "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        );

        let response = self
            .raw_http
            .post(&url)
            .header("x-goog-api-key", api_key)
            .timeout(std::time::Duration::from_secs(60))
            .json(&request_body)
            .send()
            .await
            .map_err(|e| AppError::service_unavailable(format!("Gemini transcription error: {e}")))?;

        if !response.status().is_success() {
            let status = response.status();
            let body = response.text().await.unwrap_or_default();
            tracing::error!(status = %status, body = %body, "Gemini transcription error");
            return Err(AppError::service_unavailable("Audio transcription failed"));
        }

        let gemini_resp: GeminiNativeResponse = response.json().await.map_err(|e| {
            AppError::service_unavailable(format!("Failed to parse transcription response: {e}"))
        })?;

        gemini_resp
            .candidates
            .as_ref()
            .and_then(|c| c.first())
            .and_then(|c| c.content.parts.as_ref())
            .and_then(|parts| parts.iter().find_map(|p| p.text.clone()))
            .map(|t| t.trim().to_string())
            .ok_or_else(|| AppError::service_unavailable("Empty transcription response"))
    }

    pub async fn extract_memories(
        &self,
        user_message: &str,
        assistant_response: &str,
        existing_memories: &HashMap<String, String>,
    ) -> Result<HashMap<String, String>, AppError> {
        let memories_text = if existing_memories.is_empty() {
            "(none)".to_string()
        } else {
            existing_memories
                .iter()
                .map(|(k, v)| format!("- {k}: {v}"))
                .collect::<Vec<_>>()
                .join("\n")
        };

        let prompt = format!(
            r#"Extract any factual information about the user from this conversation that should be remembered for future interactions.

Examples of things to remember:
- Physical attributes: height, weight, age, appearance
- Personal information: name, location, occupation, interests
- Preferences: favorite foods, hobbies, goals
- Context: relationship status, family, pets

Recent conversation:
User: {user_message}
Assistant: {assistant_response}

Current memories:
{memories_text}

Return ONLY a JSON object with key-value pairs. Use lowercase keys with underscores (e.g., "height", "weight", "name").
If no new information was provided, return an empty object {{}}.
If information updates an existing memory, use the new value.
Format: {{"key1": "value1", "key2": "value2"}}"#
        );

        let request = CreateChatCompletionRequestArgs::default()
            .model(&self.model)
            .messages(vec![ChatCompletionRequestMessage::User(
                ChatCompletionRequestUserMessage {
                    content: ChatCompletionRequestUserMessageContent::Text(prompt),
                    name: None,
                },
            )])
            .temperature(0.1f32)
            .max_tokens(1024u32)
            .build()
            .map_err(|e| AppError::service_unavailable(format!("Failed to build request: {e}")))?;

        let response = match self.client.chat().create(request).await {
            Ok(r) => r,
            Err(e) => {
                tracing::error!(error = %e, "Memory extraction API error");
                return Ok(existing_memories.clone());
            }
        };

        let text = response
            .choices
            .first()
            .and_then(|c| c.message.content.clone())
            .unwrap_or_default();

        parse_memory_json(&text, existing_memories)
    }
}

fn build_user_content(
    text: &str,
    media_urls: &[String],
) -> ChatCompletionRequestUserMessageContent {
    if media_urls.is_empty() {
        return ChatCompletionRequestUserMessageContent::Text(text.to_string());
    }

    let mut parts: Vec<ChatCompletionRequestUserMessageContentPart> = Vec::new();

    if !text.is_empty() {
        parts.push(ChatCompletionRequestUserMessageContentPart::Text(
            ChatCompletionRequestMessageContentPartText {
                text: text.to_string(),
            },
        ));
    }

    for url in media_urls.iter().take(5) {
        parts.push(ChatCompletionRequestUserMessageContentPart::ImageUrl(
            ChatCompletionRequestMessageContentPartImage {
                image_url: ImageUrl {
                    url: url.clone(),
                    detail: None,
                },
            },
        ));
    }

    ChatCompletionRequestUserMessageContent::Array(parts)
}

fn parse_memory_json(
    text: &str,
    existing: &HashMap<String, String>,
) -> Result<HashMap<String, String>, AppError> {
    let start = text.find('{');
    let end = text.rfind('}');

    let json_str = match (start, end) {
        (Some(s), Some(e)) if s < e => &text[s..=e],
        _ => return Ok(existing.clone()),
    };

    let new_memories: HashMap<String, String> =
        serde_json::from_str(json_str).unwrap_or_default();

    if new_memories.is_empty() {
        return Ok(existing.clone());
    }

    let mut merged = existing.clone();
    merged.extend(new_memories);
    Ok(merged)
}

fn estimate_tokens(text: &str) -> i32 {
    (text.len() as f64 / 4.0).ceil() as i32
}

// Minimal types for Gemini native API (transcription only)
#[derive(Deserialize)]
struct GeminiNativeResponse {
    candidates: Option<Vec<GeminiCandidate>>,
}

#[derive(Deserialize)]
struct GeminiCandidate {
    content: GeminiContent,
}

#[derive(Deserialize)]
struct GeminiContent {
    parts: Option<Vec<GeminiPart>>,
}

#[derive(Deserialize)]
struct GeminiPart {
    text: Option<String>,
}
