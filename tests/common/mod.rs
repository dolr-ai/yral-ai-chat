#![allow(dead_code)]

use base64::{Engine, engine::general_purpose::URL_SAFE_NO_PAD};
use reqwest::Client;
use serde_json::json;
use std::time::{SystemTime, UNIX_EPOCH};

/// Get the base URL from TEST_API_URL env var, or panic.
pub fn base_url() -> String {
    std::env::var("TEST_API_URL").expect("TEST_API_URL must be set to run integration tests")
}

/// Build a reusable HTTP client.
pub fn http_client() -> Client {
    Client::builder()
        .timeout(std::time::Duration::from_secs(30))
        .build()
        .expect("Failed to build HTTP client")
}

/// Encode bytes as base64url (no padding).
fn b64url(data: &[u8]) -> String {
    URL_SAFE_NO_PAD.encode(data)
}

/// Create a dummy RS256-style JWT. The Rust backend disables signature validation,
/// so we only need a structurally valid JWT with correct claims.
pub fn encode_jwt(payload: &serde_json::Value) -> String {
    let header = json!({"typ": "JWT", "alg": "RS256", "kid": "default"});
    let header_b64 = b64url(header.to_string().as_bytes());
    let payload_b64 = b64url(payload.to_string().as_bytes());
    format!("{header_b64}.{payload_b64}.dummy_signature")
}

/// Generate a test JWT token for the given user_id.
pub fn generate_test_token(user_id: &str) -> String {
    let now = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_secs();

    let payload = json!({
        "sub": user_id,
        "iss": "https://auth.yral.com",
        "iat": now,
        "exp": now + 3600,
    });
    encode_jwt(&payload)
}

/// Generate an expired JWT token.
pub fn generate_expired_token(user_id: &str) -> String {
    let now = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_secs();

    let payload = json!({
        "sub": user_id,
        "iss": "https://auth.yral.com",
        "iat": now.saturating_sub(7200),
        "exp": now.saturating_sub(3600),
    });
    encode_jwt(&payload)
}

/// Generate a token with a custom issuer.
pub fn generate_token_with_issuer(user_id: &str, issuer: &str) -> String {
    let now = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_secs();

    let payload = json!({
        "sub": user_id,
        "iss": issuer,
        "iat": now,
        "exp": now + 3600,
    });
    encode_jwt(&payload)
}

/// Generate a token missing the `sub` claim.
pub fn generate_token_without_sub() -> String {
    let now = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_secs();

    let payload = json!({
        "iss": "https://auth.yral.com",
        "iat": now,
        "exp": now + 3600,
    });
    encode_jwt(&payload)
}

/// Return `Authorization: Bearer <token>` header value.
pub fn auth_header(user_id: &str) -> String {
    format!("Bearer {}", generate_test_token(user_id))
}

/// Get a valid influencer ID from the API.
pub async fn get_test_influencer_id(client: &Client, base: &str) -> String {
    let resp = client
        .get(format!("{base}/api/v1/influencers?limit=1"))
        .send()
        .await
        .expect("Failed to list influencers");
    assert_eq!(resp.status(), 200);
    let data: serde_json::Value = resp.json().await.unwrap();
    assert!(data["total"].as_i64().unwrap() > 0, "No influencers in DB");
    data["influencers"][0]["id"].as_str().unwrap().to_string()
}

/// Create a test conversation and return its ID.
pub async fn create_test_conversation(
    client: &Client,
    base: &str,
    user_id: &str,
    influencer_id: &str,
) -> String {
    let resp = client
        .post(format!("{base}/api/v1/chat/conversations"))
        .header("Authorization", auth_header(user_id))
        .json(&json!({"influencer_id": influencer_id}))
        .send()
        .await
        .expect("Failed to create conversation");
    assert_eq!(resp.status(), 201);
    let data: serde_json::Value = resp.json().await.unwrap();
    data["id"].as_str().unwrap().to_string()
}

/// Unique user ID for test isolation.
pub fn unique_user() -> String {
    let ts = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_millis();
    format!("test_user_{ts}")
}

/// Unique bot ID for test isolation.
pub fn unique_bot_id() -> String {
    let ts = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_millis();
    format!("test-bot-{ts}")
}
