use std::sync::Arc;

use axum::body::Bytes;
use axum::extract::State;
use axum::http::{HeaderMap, StatusCode};
use axum::Json;
use hmac::{Hmac, Mac};
use sha2::Sha256;

use crate::AppState;

type HmacSha256 = Hmac<Sha256>;

pub async fn sentry_webhook(
    State(state): State<Arc<AppState>>,
    headers: HeaderMap,
    body: Bytes,
) -> (StatusCode, Json<serde_json::Value>) {
    let secret = match &state.settings.sentry_webhook_secret {
        Some(s) => s,
        None => {
            tracing::warn!("Sentry webhook received but SENTRY_WEBHOOK_SECRET not configured");
            return (
                StatusCode::FORBIDDEN,
                Json(serde_json::json!({"error": "Webhook secret not configured"})),
            );
        }
    };

    // Extract headers
    let signature = headers
        .get("Sentry-Hook-Signature")
        .and_then(|v| v.to_str().ok())
        .unwrap_or("");

    let resource = headers
        .get("Sentry-Hook-Resource")
        .and_then(|v| v.to_str().ok())
        .unwrap_or("unknown");

    // Verify HMAC-SHA256 signature
    let mut mac =
        HmacSha256::new_from_slice(secret.as_bytes()).expect("HMAC can take key of any size");
    mac.update(&body);
    let expected = hex::encode(mac.finalize().into_bytes());

    if signature != expected {
        tracing::warn!(resource = %resource, "Sentry webhook signature mismatch");
        return (
            StatusCode::UNAUTHORIZED,
            Json(serde_json::json!({"error": "Invalid signature"})),
        );
    }

    // Parse body to extract action
    let action = serde_json::from_slice::<serde_json::Value>(&body)
        .ok()
        .and_then(|v| v.get("action")?.as_str().map(String::from))
        .unwrap_or_else(|| "unknown".to_string());

    tracing::info!(resource = %resource, action = %action, "Sentry webhook received");

    (
        StatusCode::OK,
        Json(serde_json::json!({"status": "accepted"})),
    )
}
