use axum::{
    Json,
    extract::FromRequestParts,
    http::{StatusCode, header::AUTHORIZATION, request::Parts},
    response::{IntoResponse, Response},
};
use jsonwebtoken::{Algorithm, DecodingKey, Validation, decode};
use serde::{Deserialize, Serialize};

const EXPECTED_ISSUERS: &[&str] = &["https://auth.yral.com", "https://auth.dolr.ai"];

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct JwtPayload {
    pub sub: String,
    pub iss: String,
    pub exp: u64,
    pub iat: Option<u64>,
    pub aud: Option<String>,
    pub jti: Option<String>,
}

#[derive(Debug, Clone)]
pub struct AuthenticatedUser {
    pub user_id: String,
}

/// Rejection type for auth errors that serializes as `{"detail": "..."}` to match Python's FastAPI.
pub struct AuthRejection(pub StatusCode, pub String);

impl IntoResponse for AuthRejection {
    fn into_response(self) -> Response {
        (self.0, Json(serde_json::json!({"detail": self.1}))).into_response()
    }
}

/// Decode and validate a JWT token. Returns the claims payload or an error message string.
pub fn decode_jwt(token: &str) -> Result<JwtPayload, String> {
    let mut validation = Validation::new(Algorithm::RS256);
    validation.insecure_disable_signature_validation();
    validation.set_issuer(EXPECTED_ISSUERS);
    validation.set_required_spec_claims(&["exp", "sub", "iss"]);
    validation.validate_aud = false;

    let token_data = decode::<JwtPayload>(token, &DecodingKey::from_secret(b""), &validation)
        .map_err(|e| format!("Invalid token: {e}"))?;

    let payload = token_data.claims;

    if payload.sub.is_empty() {
        return Err("Invalid token: missing sub".to_string());
    }

    Ok(payload)
}

impl<S> FromRequestParts<S> for AuthenticatedUser
where
    S: Send + Sync,
{
    type Rejection = AuthRejection;

    async fn from_request_parts(parts: &mut Parts, _state: &S) -> Result<Self, Self::Rejection> {
        let auth_header = parts
            .headers
            .get(AUTHORIZATION)
            .and_then(|v| v.to_str().ok())
            .ok_or_else(|| {
                AuthRejection(
                    StatusCode::UNAUTHORIZED,
                    "Missing authorization header".to_string(),
                )
            })?;

        let token = auth_header
            .strip_prefix("Bearer ")
            .or_else(|| auth_header.strip_prefix("bearer "))
            .ok_or_else(|| {
                AuthRejection(
                    StatusCode::UNAUTHORIZED,
                    "Invalid authorization header format. Expected: Bearer <token>".to_string(),
                )
            })?;

        let claims =
            decode_jwt(token).map_err(|msg| AuthRejection(StatusCode::UNAUTHORIZED, msg))?;

        Ok(Self {
            user_id: claims.sub,
        })
    }
}
