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
    format!("testbot{ts}")
}

/// Upload a test image via /api/v1/media/upload and return the storage_key.
/// Returns None if S3 is unavailable (503).
pub async fn upload_test_image(client: &Client, base: &str, user_id: &str) -> Option<String> {
    use reqwest::multipart;

    // Minimal 1x1 white JPEG
    let jpeg_bytes: Vec<u8> = vec![
        0xFF, 0xD8, 0xFF, 0xE0, 0x00, 0x10, 0x4A, 0x46, 0x49, 0x46, 0x00, 0x01, 0x01, 0x00, 0x00,
        0x01, 0x00, 0x01, 0x00, 0x00, 0xFF, 0xDB, 0x00, 0x43, 0x00, 0x08, 0x06, 0x06, 0x07, 0x06,
        0x05, 0x08, 0x07, 0x07, 0x07, 0x09, 0x09, 0x08, 0x0A, 0x0C, 0x14, 0x0D, 0x0C, 0x0B, 0x0B,
        0x0C, 0x19, 0x12, 0x13, 0x0F, 0x14, 0x1D, 0x1A, 0x1F, 0x1E, 0x1D, 0x1A, 0x1C, 0x1C, 0x20,
        0x24, 0x2E, 0x27, 0x20, 0x22, 0x2C, 0x23, 0x1C, 0x1C, 0x28, 0x37, 0x29, 0x2C, 0x30, 0x31,
        0x34, 0x34, 0x34, 0x1F, 0x27, 0x39, 0x3D, 0x38, 0x32, 0x3C, 0x2E, 0x33, 0x34, 0x32, 0xFF,
        0xC0, 0x00, 0x0B, 0x08, 0x00, 0x01, 0x00, 0x01, 0x01, 0x01, 0x11, 0x00, 0xFF, 0xC4, 0x00,
        0x1F, 0x00, 0x00, 0x01, 0x05, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x09, 0x0A, 0x0B,
        0xFF, 0xDA, 0x00, 0x08, 0x01, 0x01, 0x00, 0x00, 0x3F, 0x00, 0x7B, 0x94, 0x11, 0x00, 0x00,
        0x00, 0x00, 0x00, 0xFF, 0xD9,
    ];

    let form = multipart::Form::new().text("type", "image").part(
        "file",
        multipart::Part::bytes(jpeg_bytes)
            .file_name("test.jpg")
            .mime_str("image/jpeg")
            .unwrap(),
    );

    let resp = client
        .post(format!("{base}/api/v1/media/upload"))
        .header("Authorization", auth_header(user_id))
        .multipart(form)
        .send()
        .await
        .unwrap();

    if resp.status().as_u16() == 200 {
        let data: serde_json::Value = resp.json().await.unwrap();
        Some(data["storage_key"].as_str().unwrap().to_string())
    } else {
        None
    }
}

/// Upload a test audio file via /api/v1/media/upload and return the storage_key.
/// Returns None if S3 is unavailable (503).
pub async fn upload_test_audio(client: &Client, base: &str, user_id: &str) -> Option<String> {
    use reqwest::multipart;

    // Minimal MP3 frame (valid MPEG audio frame header + padding)
    let mp3_bytes: Vec<u8> = vec![
        0xFF, 0xFB, 0x90, 0x00, // MPEG1 Layer3 128kbps 44100Hz stereo frame header
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    ];

    let form = multipart::Form::new().text("type", "audio").part(
        "file",
        multipart::Part::bytes(mp3_bytes)
            .file_name("test.mp3")
            .mime_str("audio/mpeg")
            .unwrap(),
    );

    let resp = client
        .post(format!("{base}/api/v1/media/upload"))
        .header("Authorization", auth_header(user_id))
        .multipart(form)
        .send()
        .await
        .unwrap();

    if resp.status().as_u16() == 200 {
        let data: serde_json::Value = resp.json().await.unwrap();
        Some(data["storage_key"].as_str().unwrap().to_string())
    } else {
        None
    }
}

/// Generate a short alphanumeric name suitable for influencer creation (3-15 chars).
pub fn unique_bot_name(prefix: &str) -> String {
    let ts = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_millis();
    let suffix = format!("{ts}");
    // Take last N digits to fit within 15 chars
    let max_suffix = 15 - prefix.len();
    let start = suffix.len().saturating_sub(max_suffix);
    format!("{prefix}{}", &suffix[start..])
}
