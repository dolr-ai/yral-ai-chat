use std::collections::HashMap;
use std::sync::Arc;

use axum::extract::State;
use axum::Json;
use chrono::Utc;

use crate::models::responses::{
    DatabaseStats, HealthResponse, ServiceHealth, StatusResponse, SystemStatistics,
};
use crate::AppState;

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
        environment: state.settings.environment.as_str().to_string(),
        uptime_seconds: uptime,
        database: DatabaseStats {
            connected: true,
            pool_size: Some(state.settings.database_pool_size),
        },
        statistics: SystemStatistics {
            total_conversations,
            total_messages,
            active_influencers,
        },
        timestamp: Utc::now().naive_utc(),
    })
}

pub async fn root(State(state): State<Arc<AppState>>) -> Json<serde_json::Value> {
    Json(serde_json::json!({
        "service": state.settings.app_name,
        "version": state.settings.app_version,
        "docs": "/docs",
    }))
}
