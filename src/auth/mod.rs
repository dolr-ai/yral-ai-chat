use axum::{
    extract::FromRequestParts,
    http::{header::AUTHORIZATION, request::Parts},
};
use jsonwebtoken::{decode, Algorithm, DecodingKey, Validation};
use serde::{Deserialize, Serialize};

use crate::error::AppError;

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

fn decode_jwt(token: &str) -> Result<JwtPayload, AppError> {
    let mut validation = Validation::new(Algorithm::RS256);
    validation.insecure_disable_signature_validation();
    validation.set_issuer(EXPECTED_ISSUERS);
    validation.set_required_spec_claims(&["exp", "sub", "iss"]);
    validation.validate_aud = false;

    let token_data = decode::<JwtPayload>(token, &DecodingKey::from_secret(b""), &validation)
        .map_err(|e| AppError::unauthorized(format!("Invalid token: {e}")))?;

    let payload = token_data.claims;

    if payload.sub.is_empty() {
        return Err(AppError::unauthorized("Invalid token: missing sub"));
    }

    Ok(payload)
}

impl<S> FromRequestParts<S> for AuthenticatedUser
where
    S: Send + Sync,
{
    type Rejection = AppError;

    async fn from_request_parts(parts: &mut Parts, _state: &S) -> Result<Self, Self::Rejection> {
        let auth_header = parts
            .headers
            .get(AUTHORIZATION)
            .and_then(|v| v.to_str().ok())
            .ok_or_else(|| AppError::unauthorized("Missing authorization header"))?;

        let token = auth_header
            .strip_prefix("Bearer ")
            .or_else(|| auth_header.strip_prefix("bearer "))
            .ok_or_else(|| {
                AppError::unauthorized(
                    "Invalid authorization header format. Expected: Bearer <token>",
                )
            })?;

        let claims = decode_jwt(token)?;

        Ok(Self { user_id: claims.sub })
    }
}
