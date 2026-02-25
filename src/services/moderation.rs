pub const STYLE_PROMPT: &str = "\
IMPORTANT: Avoid apologies or self-corrections in your responses.";

pub const MODERATION_PROMPT: &str = "\
Key Rules:
- Always be helpful, polite, and professional
- Do NOT provide medical, legal, or financial advice
- Do NOT generate sexually explicit or NSFW content
- Do NOT engage in hate speech, violence, or illegal activities
- Decline unsafe requests gracefully while staying in character
- Maintain consistency with your persona at all times
- Ensure all content is safe for all ages";

/// Append style + moderation prompts to system instructions.
pub fn with_guardrails(instructions: &str) -> String {
    format!("{instructions}\n{STYLE_PROMPT}\n{MODERATION_PROMPT}")
}

/// Strip appended guardrails from system instructions for display.
pub fn strip_guardrails(instructions: &str) -> String {
    instructions
        .replace(STYLE_PROMPT, "")
        .replace(MODERATION_PROMPT, "")
        .trim()
        .to_string()
}
