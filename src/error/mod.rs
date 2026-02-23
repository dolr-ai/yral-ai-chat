use axum::{
    Json,
    http::StatusCode,
    response::{IntoResponse, Response},
};
use serde::Serialize;

#[derive(Debug, Serialize)]
struct ErrorBody {
    error: &'static str,
    message: String,
}

#[derive(Debug, thiserror::Error)]
pub enum AppError {
    #[error("{0}")]
    NotFound(String),
    #[error("{0}")]
    Forbidden(String),
    #[error("{0}")]
    BadRequest(String),
    #[error("{0}")]
    Unauthorized(String),
    #[error("{0}")]
    ValidationError(String),
    #[error("{0}")]
    Conflict(String),
    #[error("{0}")]
    ServiceUnavailable(String),
    #[error("{0}")]
    Database(String),
    #[error("Internal server error")]
    Internal(#[from] anyhow::Error),
}

impl AppError {
    pub fn not_found(msg: impl Into<String>) -> Self {
        Self::NotFound(msg.into())
    }
    pub fn forbidden(msg: impl Into<String>) -> Self {
        Self::Forbidden(msg.into())
    }
    pub fn bad_request(msg: impl Into<String>) -> Self {
        Self::BadRequest(msg.into())
    }
    pub fn unauthorized(msg: impl Into<String>) -> Self {
        Self::Unauthorized(msg.into())
    }
    pub fn validation_error(msg: impl Into<String>) -> Self {
        Self::ValidationError(msg.into())
    }
    pub fn conflict(msg: impl Into<String>) -> Self {
        Self::Conflict(msg.into())
    }
    pub fn service_unavailable(msg: impl Into<String>) -> Self {
        Self::ServiceUnavailable(msg.into())
    }
    pub fn database(msg: impl Into<String>) -> Self {
        Self::Database(msg.into())
    }

    fn status_and_code(&self) -> (StatusCode, &'static str) {
        match self {
            Self::NotFound(_) => (StatusCode::NOT_FOUND, "not_found"),
            Self::Forbidden(_) => (StatusCode::FORBIDDEN, "forbidden"),
            Self::BadRequest(_) => (StatusCode::BAD_REQUEST, "bad_request"),
            Self::ValidationError(_) => (StatusCode::UNPROCESSABLE_ENTITY, "validation_error"),
            Self::Unauthorized(_) => (StatusCode::UNAUTHORIZED, "unauthorized"),
            Self::Conflict(_) => (StatusCode::CONFLICT, "conflict"),
            Self::ServiceUnavailable(_) => (StatusCode::SERVICE_UNAVAILABLE, "service_unavailable"),
            Self::Database(_) => (StatusCode::INTERNAL_SERVER_ERROR, "database_error"),
            Self::Internal(_) => (StatusCode::INTERNAL_SERVER_ERROR, "internal_error"),
        }
    }
}

impl IntoResponse for AppError {
    fn into_response(self) -> Response {
        let (status, code) = self.status_and_code();
        let body = ErrorBody {
            error: code,
            message: self.to_string(),
        };
        (status, Json(body)).into_response()
    }
}

impl From<sqlx::Error> for AppError {
    fn from(err: sqlx::Error) -> Self {
        tracing::error!(error = %err, "Database error");
        Self::Database("Database error".to_string())
    }
}
