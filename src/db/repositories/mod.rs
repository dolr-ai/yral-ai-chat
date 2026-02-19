pub mod influencer_repository;
pub mod conversation_repository;
pub mod message_repository;

pub use influencer_repository::InfluencerRepository;
pub use conversation_repository::ConversationRepository;
pub use message_repository::MessageRepository;

/// Parse a SQLite datetime string into NaiveDateTime.
pub(crate) fn parse_dt(s: &str) -> chrono::NaiveDateTime {
    chrono::NaiveDateTime::parse_from_str(s, "%Y-%m-%d %H:%M:%S").unwrap_or_default()
}

/// Parse a JSON string, returning an empty object on failure.
pub(crate) fn parse_json(s: &str) -> serde_json::Value {
    serde_json::from_str(s).unwrap_or(serde_json::Value::Object(Default::default()))
}
