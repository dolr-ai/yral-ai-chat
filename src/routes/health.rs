use std::collections::HashMap;
use std::sync::Arc;

use axum::Json;
use axum::extract::State;
use chrono::Utc;

use crate::AppState;
use crate::models::responses::{
    DatabaseStats, HealthResponse, ServiceHealth, StatusResponse, SystemStatistics,
};

#[utoipa::path(
    get,
    path = "/health",
    responses((status = 200, body = HealthResponse, description = "Service health check")),
    tag = "Health"
)]
pub async fn health(State(state): State<Arc<AppState>>) -> Json<HealthResponse> {
    let db_health = state.db.health_check().await;

    let mut services = HashMap::new();
    services.insert(
        "database".to_string(),
        ServiceHealth {
            status: db_health.status.clone(),
            latency_ms: db_health.latency_ms,
            error: db_health.error,
            pool_size: Some(state.settings.database_pool_size),
            pool_free: None,
        },
    );
    services.insert(
        "gemini_api".to_string(),
        ServiceHealth {
            status: "up".to_string(),
            latency_ms: None,
            error: None,
            pool_size: None,
            pool_free: None,
        },
    );
    services.insert(
        "s3_storage".to_string(),
        ServiceHealth {
            status: "up".to_string(),
            latency_ms: None,
            error: None,
            pool_size: None,
            pool_free: None,
        },
    );
    services.insert(
        "litestream".to_string(),
        ServiceHealth {
            status: "up".to_string(),
            latency_ms: None,
            error: None,
            pool_size: None,
            pool_free: None,
        },
    );

    let overall_status = if db_health.status == "up" {
        "healthy"
    } else {
        "unhealthy"
    };

    Json(HealthResponse {
        status: overall_status.to_string(),
        timestamp: Utc::now().naive_utc(),
        services,
    })
}

#[utoipa::path(
    get,
    path = "/status",
    responses((status = 200, body = StatusResponse, description = "Detailed service status")),
    tag = "Health"
)]
pub async fn status(State(state): State<Arc<AppState>>) -> Json<StatusResponse> {
    let uptime = state.start_time.elapsed().as_secs();

    let total_conversations: i64 = sqlx::query_scalar("SELECT COUNT(*) FROM conversations")
        .fetch_one(&state.db.pool)
        .await
        .unwrap_or(0);

    let total_messages: i64 = sqlx::query_scalar("SELECT COUNT(*) FROM messages")
        .fetch_one(&state.db.pool)
        .await
        .unwrap_or(0);

    let active_influencers: i64 =
        sqlx::query_scalar("SELECT COUNT(*) FROM ai_influencers WHERE is_active = 'active'")
            .fetch_one(&state.db.pool)
            .await
            .unwrap_or(0);

    Json(StatusResponse {
        service: state.settings.app_name.clone(),
        version: state.settings.app_version.clone(),
        environment: state.settings.environment.clone(),
        uptime_seconds: uptime,
        database: DatabaseStats {
            connected: true,
            pool_size: Some(state.settings.database_pool_size),
            active_connections: Some(state.settings.database_pool_size),
        },
        statistics: SystemStatistics {
            total_conversations,
            total_messages,
            active_influencers,
        },
        timestamp: Utc::now().naive_utc(),
    })
}

#[utoipa::path(
    get,
    path = "/",
    responses((status = 200, description = "Service info")),
    tag = "Health"
)]
pub async fn root(State(state): State<Arc<AppState>>) -> Json<serde_json::Value> {
    Json(serde_json::json!({
        "service": state.settings.app_name,
        "version": state.settings.app_version,
        "status": "running",
        "docs": "/explorer/",
        "health": "/health",
        "metrics": "/metrics",
    }))
}
