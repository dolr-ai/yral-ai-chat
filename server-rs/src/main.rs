mod config;
mod db;
mod error;
mod models;
mod routes;

use std::sync::Arc;
use std::time::Instant;

use axum::Router;
use tower_http::compression::CompressionLayer;
use tower_http::cors::{Any, CorsLayer};
use tower_http::trace::TraceLayer;

use config::Settings;
use db::Database;

pub struct AppState {
    pub db: Database,
    pub settings: Settings,
    pub start_time: Instant,
}

#[tokio::main]
async fn main() {
    // Load .env file
    dotenvy::dotenv().ok();

    // Initialize tracing
    let settings = Settings::from_env();
    init_tracing(&settings);

    tracing::info!(
        app = %settings.app_name,
        version = %settings.app_version,
        "Starting server"
    );

    // Connect to database
    let database = Database::connect(&settings)
        .await
        .expect("Failed to connect to database");

    // Run migrations
    let migrations_dir = if std::path::Path::new("/app/migrations/sqlite").exists() {
        "/app/migrations/sqlite"
    } else {
        "../migrations/sqlite"
    };

    db::run_migrations(&database.pool, migrations_dir)
        .await
        .expect("Failed to run migrations");

    // Build app state
    let state = Arc::new(AppState {
        db: database,
        settings: settings.clone(),
        start_time: Instant::now(),
    });

    // Build CORS layer
    let cors = build_cors(&settings);

    // Build router
    let app = Router::new()
        .route("/", axum::routing::get(routes::health::root))
        .route("/health", axum::routing::get(routes::health::health))
        .route("/status", axum::routing::get(routes::health::status))
        .layer(CompressionLayer::new())
        .layer(TraceLayer::new_for_http())
        .layer(cors)
        .with_state(state);

    // Start server
    let addr = format!("{}:{}", settings.host, settings.port);
    tracing::info!(address = %addr, "Server listening");

    let listener = tokio::net::TcpListener::bind(&addr)
        .await
        .expect("Failed to bind address");

    axum::serve(listener, app)
        .await
        .expect("Server error");
}

fn init_tracing(settings: &Settings) {
    use tracing_subscriber::{fmt, EnvFilter};

    let filter = EnvFilter::try_from_default_env()
        .unwrap_or_else(|_| EnvFilter::new(&settings.log_level));

    if settings.log_format == "json" {
        fmt()
            .json()
            .with_env_filter(filter)
            .with_target(true)
            .with_thread_ids(false)
            .with_file(false)
            .with_line_number(false)
            .init();
    } else {
        fmt()
            .with_env_filter(filter)
            .with_target(true)
            .init();
    }
}

fn build_cors(settings: &Settings) -> CorsLayer {
    let origins = settings.cors_origins_list();

    if origins.contains(&"*".to_string()) {
        CorsLayer::new()
            .allow_origin(Any)
            .allow_methods(Any)
            .allow_headers(Any)
    } else {
        let allowed: Vec<_> = origins
            .iter()
            .filter_map(|o| o.parse().ok())
            .collect();
        CorsLayer::new()
            .allow_origin(allowed)
            .allow_methods(Any)
            .allow_headers(Any)
            .allow_credentials(true)
    }
}
