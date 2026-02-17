use axum::{
    http::StatusCode,
    response::{IntoResponse, Response},
    Json,
};
use serde::Serialize;

#[derive(Debug, Serialize)]
pub struct ErrorBody {
    pub error: String,
    pub message: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub details: Option<serde_json::Value>,
}

#[derive(Debug, thiserror::Error)]
pub enum AppError {
    #[error("{message}")]
    NotFound {
        message: String,
        details: Option<serde_json::Value>,
    },

    #[error("{message}")]
    Forbidden {
        message: String,
        details: Option<serde_json::Value>,
    },

    #[error("{message}")]
    BadRequest {
        message: String,
        details: Option<serde_json::Value>,
    },

    #[error("{message}")]
    Unauthorized {
        message: String,
        details: Option<serde_json::Value>,
    },

    #[error("{message}")]
    AIService {
        message: String,
        details: Option<serde_json::Value>,
    },

    #[error("{message}")]
    Transcription {
        message: String,
        details: Option<serde_json::Value>,
    },

    #[error("{message}")]
    RateLimit {
        message: String,
        details: Option<serde_json::Value>,
    },

    #[error("{message}")]
    Validation {
        message: String,
        details: Option<serde_json::Value>,
    },

    #[error("{message}")]
    Database {
        message: String,
        details: Option<serde_json::Value>,
    },

    #[error("{message}")]
    Conflict {
        message: String,
        details: Option<serde_json::Value>,
    },

    #[error("{message}")]
    ServiceUnavailable {
        message: String,
        details: Option<serde_json::Value>,
    },

    #[error("Internal server error")]
    Internal(#[from] anyhow::Error),
}

impl AppError {
    fn status_code(&self) -> StatusCode {
        match self {
            Self::NotFound { .. } => StatusCode::NOT_FOUND,
            Self::Forbidden { .. } => StatusCode::FORBIDDEN,
            Self::BadRequest { .. } => StatusCode::BAD_REQUEST,
            Self::Unauthorized { .. } => StatusCode::UNAUTHORIZED,
            Self::AIService { .. } => StatusCode::INTERNAL_SERVER_ERROR,
            Self::Transcription { .. } => StatusCode::INTERNAL_SERVER_ERROR,
            Self::RateLimit { .. } => StatusCode::TOO_MANY_REQUESTS,
            Self::Validation { .. } => StatusCode::UNPROCESSABLE_ENTITY,
            Self::Database { .. } => StatusCode::INTERNAL_SERVER_ERROR,
            Self::Conflict { .. } => StatusCode::CONFLICT,
            Self::ServiceUnavailable { .. } => StatusCode::SERVICE_UNAVAILABLE,
            Self::Internal(_) => StatusCode::INTERNAL_SERVER_ERROR,
        }
    }

    fn error_code(&self) -> &str {
        match self {
            Self::NotFound { .. } => "not_found",
            Self::Forbidden { .. } => "forbidden",
            Self::BadRequest { .. } => "bad_request",
            Self::Unauthorized { .. } => "unauthorized",
            Self::AIService { .. } => "ai_service_error",
            Self::Transcription { .. } => "transcription_error",
            Self::RateLimit { .. } => "rate_limit_exceeded",
            Self::Validation { .. } => "validation_error",
            Self::Database { .. } => "database_error",
            Self::Conflict { .. } => "conflict",
            Self::ServiceUnavailable { .. } => "service_unavailable",
            Self::Internal(_) => "internal_error",
        }
    }

    fn details(&self) -> Option<serde_json::Value> {
        match self {
            Self::NotFound { details, .. }
            | Self::Forbidden { details, .. }
            | Self::BadRequest { details, .. }
            | Self::Unauthorized { details, .. }
            | Self::AIService { details, .. }
            | Self::Transcription { details, .. }
            | Self::RateLimit { details, .. }
            | Self::Validation { details, .. }
            | Self::Database { details, .. }
            | Self::Conflict { details, .. }
            | Self::ServiceUnavailable { details, .. } => details.clone(),
            Self::Internal(_) => None,
        }
    }

    pub fn not_found(message: impl Into<String>) -> Self {
        Self::NotFound {
            message: message.into(),
            details: None,
        }
    }

    pub fn forbidden(message: impl Into<String>) -> Self {
        Self::Forbidden {
            message: message.into(),
            details: None,
        }
    }

    pub fn bad_request(message: impl Into<String>) -> Self {
        Self::BadRequest {
            message: message.into(),
            details: None,
        }
    }

    pub fn unauthorized(message: impl Into<String>) -> Self {
        Self::Unauthorized {
            message: message.into(),
            details: None,
        }
    }

    pub fn database(message: impl Into<String>) -> Self {
        Self::Database {
            message: message.into(),
            details: None,
        }
    }

    pub fn conflict(message: impl Into<String>) -> Self {
        Self::Conflict {
            message: message.into(),
            details: None,
        }
    }

    pub fn service_unavailable(message: impl Into<String>) -> Self {
        Self::ServiceUnavailable {
            message: message.into(),
            details: None,
        }
    }
}

impl IntoResponse for AppError {
    fn into_response(self) -> Response {
        let status = self.status_code();
        let body = ErrorBody {
            error: self.error_code().to_string(),
            message: self.to_string(),
            details: self.details(),
        };

        (status, Json(body)).into_response()
    }
}

impl From<sqlx::Error> for AppError {
    fn from(err: sqlx::Error) -> Self {
        tracing::error!(error = %err, "Database error");
        Self::Database {
            message: "Database error".to_string(),
            details: None,
        }
    }
}
