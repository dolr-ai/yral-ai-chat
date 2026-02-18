use serde::Deserialize;

use crate::error::AppError;
use crate::models::responses::GeneratedMetadataResponse;
use crate::services::ai::AiClient;
use crate::services::replicate::ReplicateClient;

const GENERATE_PROMPT: &str = r#"You are an AI character designer. Given a character concept, create detailed system instructions for an AI chatbot persona.

The system instructions should:
1. Define the character's personality, speaking style, and background
2. Include specific behavioral guidelines
3. Be written in second person ("You are...")
4. Be concise but comprehensive (max 500 words)
5. Make the character feel authentic and engaging

Return ONLY the system instructions text, nothing else."#;

const VALIDATE_PROMPT: &str = r#"You are a character validator. Analyze the given system instructions and generate metadata.

Rules:
- The character MUST NOT be sexually explicit or NSFW
- The character must be safe for all ages
- Generate a URL-friendly name (3-12 lowercase alphanumeric characters only)
- Generate a display name (human-readable)
- Generate a one-line description
- Generate an initial greeting message (can use Hinglish)
- Generate 3-4 suggested starter messages (can use Hinglish)
- Generate personality traits as key-value pairs
- Suggest a category
- Generate an image prompt for avatar creation

Return a JSON object with this exact schema:
{
  "is_valid": true/false,
  "reason": "reason if invalid, null if valid",
  "name": "urlslug",
  "display_name": "Display Name",
  "description": "One line description",
  "initial_greeting": "Hi! I'm...",
  "suggested_messages": ["msg1", "msg2", "msg3"],
  "personality_traits": [{"trait": "energy_level", "value": "high"}],
  "category": "entertainment",
  "image_prompt": "portrait of..."
}"#;

const GREETING_PROMPT: &str = r#"Generate an initial greeting message and 3-4 suggested starter messages for a chatbot character.

Character name: {display_name}
System instructions: {system_instructions}

Return a JSON object:
{
  "initial_greeting": "greeting message (can use Hinglish)",
  "suggested_messages": ["msg1", "msg2", "msg3", "msg4"]
}"#;

const VIDEO_PROMPT: &str = r#"Generate a 1-2 sentence starter video prompt for this character. It should describe a short intro video scene.

Character: {display_name}
Instructions: {system_instructions}

Return ONLY the video prompt text."#;

const SAFETY_REFUSALS: &[&str] = &[
    "i cannot create",
    "i can't create",
    "sexually suggestive",
    "inappropriate",
    "i cannot generate",
    "i can't generate",
    "not appropriate",
    "violates",
    "harmful",
];

#[derive(Deserialize)]
struct ValidationResult {
    is_valid: Option<bool>,
    reason: Option<String>,
    name: Option<String>,
    display_name: Option<String>,
    description: Option<String>,
    initial_greeting: Option<String>,
    suggested_messages: Option<Vec<String>>,
    personality_traits: Option<serde_json::Value>,
    category: Option<String>,
    image_prompt: Option<String>,
}

#[derive(Deserialize)]
struct GreetingResult {
    initial_greeting: Option<String>,
    suggested_messages: Option<Vec<String>>,
}

pub struct CharacterGeneratorService;

impl CharacterGeneratorService {
    pub async fn generate_system_instructions(
        gemini: &AiClient,
        prompt: &str,
    ) -> Result<String, AppError> {
        let (text, _) = gemini
            .generate_response(prompt, GENERATE_PROMPT, &[], None)
            .await?;
        Ok(text)
    }

    pub async fn validate_and_generate_metadata(
        gemini: &AiClient,
        replicate: &ReplicateClient,
        system_instructions: &str,
    ) -> Result<GeneratedMetadataResponse, AppError> {
        // Check for safety refusals in the input
        let lower = system_instructions.to_lowercase();
        for refusal in SAFETY_REFUSALS {
            if lower.contains(refusal) {
                return Ok(GeneratedMetadataResponse {
                    is_valid: false,
                    reason: Some("Content failed safety validation".to_string()),
                    name: None,
                    display_name: None,
                    description: None,
                    avatar_url: None,
                    initial_greeting: None,
                    suggested_messages: None,
                    personality_traits: None,
                    category: None,
                });
            }
        }

        let (text, _) = gemini
            .generate_response(system_instructions, VALIDATE_PROMPT, &[], None)
            .await?;

        // Check response for safety refusals
        let lower_resp = text.to_lowercase();
        for refusal in SAFETY_REFUSALS {
            if lower_resp.contains(refusal) {
                return Ok(GeneratedMetadataResponse {
                    is_valid: false,
                    reason: Some("Content failed safety validation".to_string()),
                    name: None,
                    display_name: None,
                    description: None,
                    avatar_url: None,
                    initial_greeting: None,
                    suggested_messages: None,
                    personality_traits: None,
                    category: None,
                });
            }
        }

        // Parse JSON from response
        let result: ValidationResult = parse_json_from_response(&text).unwrap_or(ValidationResult {
            is_valid: Some(false),
            reason: Some("Failed to parse validation response".to_string()),
            name: None,
            display_name: None,
            description: None,
            initial_greeting: None,
            suggested_messages: None,
            personality_traits: None,
            category: None,
            image_prompt: None,
        });

        if !result.is_valid.unwrap_or(false) {
            return Ok(GeneratedMetadataResponse {
                is_valid: false,
                reason: result.reason,
                name: None,
                display_name: None,
                description: None,
                avatar_url: None,
                initial_greeting: None,
                suggested_messages: None,
                personality_traits: None,
                category: None,
            });
        }

        // Generate avatar via Replicate if image_prompt available
        let avatar_url = if let Some(ref img_prompt) = result.image_prompt {
            if replicate.is_configured() {
                let enhanced = format!(
                    "Professional avatar portrait, high quality, {img_prompt}"
                );
                match replicate.generate_image(&enhanced, "1:1").await {
                    Ok(url) => url,
                    Err(e) => {
                        tracing::error!(error = %e, "Avatar generation failed");
                        None
                    }
                }
            } else {
                None
            }
        } else {
            None
        };

        Ok(GeneratedMetadataResponse {
            is_valid: true,
            reason: None,
            name: result.name,
            display_name: result.display_name,
            description: result.description,
            avatar_url,
            initial_greeting: result.initial_greeting,
            suggested_messages: result.suggested_messages,
            personality_traits: result.personality_traits,
            category: result.category,
        })
    }

    pub async fn generate_initial_greeting(
        gemini: &AiClient,
        display_name: &str,
        system_instructions: &str,
    ) -> Result<(String, Vec<String>), AppError> {
        let prompt = GREETING_PROMPT
            .replace("{display_name}", display_name)
            .replace("{system_instructions}", system_instructions);

        let (text, _) = gemini
            .generate_response(&prompt, "You are a helpful assistant that returns valid JSON.", &[], None)
            .await?;

        let result: GreetingResult = parse_json_from_response(&text).unwrap_or(GreetingResult {
            initial_greeting: None,
            suggested_messages: None,
        });

        let greeting = result
            .initial_greeting
            .unwrap_or_else(|| format!("Hey! I'm {display_name}! How can I help you today?"));
        let suggestions = result.suggested_messages.unwrap_or_default();

        Ok((greeting, suggestions))
    }

    pub async fn generate_starter_video_prompt(
        gemini: &AiClient,
        display_name: &str,
        system_instructions: &str,
    ) -> Result<String, AppError> {
        let prompt = VIDEO_PROMPT
            .replace("{display_name}", display_name)
            .replace("{system_instructions}", system_instructions);

        let (text, _) = gemini
            .generate_response(&prompt, "You are a helpful assistant.", &[], None)
            .await?;

        Ok(text.trim().to_string())
    }
}

fn parse_json_from_response<T: serde::de::DeserializeOwned>(text: &str) -> Option<T> {
    let start = text.find('{')?;
    let end = text.rfind('}')?;
    if start >= end {
        return None;
    }
    serde_json::from_str(&text[start..=end]).ok()
}
