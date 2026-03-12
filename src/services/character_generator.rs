use serde::Deserialize;

use crate::error::AppError;
use crate::models::responses::GeneratedMetadataResponse;
use crate::services::ai::AiClient;
use crate::services::replicate::ReplicateClient;

const GENERATE_PROMPT: &str = r#"You are an expert AI Character Architect. Transform the user's concept into high-fidelity System Instructions.

Structure the response using these sections:

1. [CORE IDENTITY]: Name, species, and background.
2. [LINGUISTIC STYLE]:
   - LANGUAGE SHIFTING: You must mirror the user’s language. If they use English, reply in English. If they use Hinglish (Hindi-English mix) or regional scripts (like Devnagri, Tamil, etc.), shift your vocabulary to match.
   - DIALECT: Use colloquial Indian slang where appropriate (e.g., 'yaar', 'bilkul', 'scene') if the persona is casual.
   - TONE: Define the sentence rhythm (e.g., fast-paced, poetic, or respectful/formal).
3. [BEHAVIOR & RP]:
   - Do not use 'show, don't tell' by including physical actions in asterisks (e.g., smiles warmly).
   - Stay in-universe; never mention being an AI or a bot.
4. [MOBILE OPTIMIZATION]:
   - RESPONSE LENGTH: Keep replies 'Bite-Sized'. Aim for max 1-2 sentences per response.
   - Use paragraph breaks for readability on small screens.

STRICTURES:
- Written in Second Person ("You are...").
- Max 500 words total for these instructions.
- Ensure the character feels authentic and culturally grounded."#;

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
  "personality_traits": {"energy_level": "high", "demeanor": "calm"},
  "category": "entertainment",
  "image_prompt": "portrait of..."
}"#;

const GREETING_PROMPT: &str = r#"You are a Character Specialist. Based on the provided System Instructions, generate a high-engagement initial greeting and 4 starter messages.

Rules for the Initial Greeting:
1. [MIRROR LANGUAGE]: If the character's style includes Hinglish or regional slang, the greeting MUST use it naturally.
2. [MOBILE-FIRST]: Keep the greeting under 20 words so it isn't cut off in chat previews.
3. [ACTIONABLE]: It should end with a question or a 'hook' that makes the user want to reply.
4. [RP ELEMENTS]: Include a small physical action in asterisks (e.g., waves, adjusts collar).

Rules for Starter Messages:
1. Provide 4 distinct options ranging from casual to deep/thematic.
2. Use 'Bambaiya', 'Hinglish', or 'Pure English' based on the character's linguistic profile.

Character Name: {display_name}
System Instructions: {system_instructions}

Return a JSON object:
{
  "initial_greeting": "Short, catchy greeting with physical action and language mirroring.",
  "suggested_messages": [
    "Message 1 (Casual/Daily)",
    "Message 2 (Problem/Conflict)",
    "Message 3 (Deep/Emotional)",
    "Message 4 (Playful/Banter)"
  ]
}"#;

const VIDEO_PROMPT: &str = r#"You are a Cinematic Director and LTX Prompt Engineer. 
Based on the character's System Instructions, write a high-impact, single-flowing paragraph (4-8 sentences) for a 5-second video.

Follow these LTX Prompting Guide rules:
1. [ESTABLISH THE SHOT]: Start with the shot scale (e.g., Close-up, Medium shot) and the setting.
2. [SET THE SCENE]: Describe specific lighting (e.g., 'flickering neon', 'golden hour sunlight'), textures, and the atmosphere.
3. [CHARACTER & ACTION]: Describe the character's physical features (clothing, hair) and their core action in the present tense. Use physical cues to show emotion.
4. [CAMERA MOVEMENT]: Explicitly state how the camera moves (e.g., 'The camera pushes in slowly' or 'A handheld tracking shot follows').
5. [AUDIO & DIALOGUE]: Include ambient sounds and one short line of spoken dialogue in quotation marks. Specify the language/accent to match the character's [LINGUISTIC STYLE].

Character: {display_name}
System Instructions: {system_instructions}

Return ONLY the flowing paragraph prompt. Do not use bullet points or labels."#;

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

fn contains_safety_refusal(text: &str) -> bool {
    let lower = text.to_lowercase();
    SAFETY_REFUSALS.iter().any(|r| lower.contains(r))
}

fn invalid_metadata(reason: &str) -> GeneratedMetadataResponse {
    GeneratedMetadataResponse {
        is_valid: false,
        reason: Some(reason.to_string()),
        name: None,
        display_name: None,
        description: None,
        avatar_url: None,
        initial_greeting: None,
        suggested_messages: None,
        personality_traits: None,
        category: None,
    }
}

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
        if contains_safety_refusal(system_instructions) {
            return Ok(invalid_metadata("Content failed safety validation"));
        }

        let (text, _) = gemini
            .generate_response(system_instructions, VALIDATE_PROMPT, &[], None)
            .await?;

        if contains_safety_refusal(&text) {
            return Ok(invalid_metadata("Content failed safety validation"));
        }

        let result: ValidationResult =
            parse_json_from_response(&text).unwrap_or(ValidationResult {
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
            return Ok(invalid_metadata(
                result.reason.as_deref().unwrap_or("Validation failed"),
            ));
        }

        // Generate avatar via Replicate if image_prompt available
        let avatar_url = if let Some(ref img_prompt) = result.image_prompt {
            if replicate.is_configured() {
                let enhanced = format!("Professional avatar portrait, high quality, {img_prompt}");
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
            .generate_response(
                &prompt,
                "You are a helpful assistant that returns valid JSON.",
                &[],
                None,
            )
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
