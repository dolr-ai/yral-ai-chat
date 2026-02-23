mod config;
mod db;
mod error;
mod middleware;
mod models;
mod routes;
mod services;

use std::sync::Arc;
use std::time::Instant;

use axum::Router;
use axum::http::header;
use tower_http::compression::CompressionLayer;
use tower_http::cors::{Any, CorsLayer};
use tower_http::trace::TraceLayer;

use config::Settings;
use db::Database;
use services::ai::AiClient;
use services::notification::PushNotificationService;
use services::replicate::ReplicateClient;
use services::storage::StorageService;
use services::websocket::WsManager;

pub struct AppState {
    pub db: Database,
    pub settings: Settings,
    pub start_time: Instant,
    pub http_client: reqwest::Client,
    pub storage: StorageService,
    pub gemini: AiClient,
    pub openrouter: AiClient,
    pub replicate: ReplicateClient,
    pub push_notifications: PushNotificationService,
    pub ws_manager: Arc<WsManager>,
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
        "./migrations/sqlite"
    };

    db::run_migrations(&database.pool, migrations_dir)
        .await
        .expect("Failed to run migrations");

    // Eager WAL checkpoint on startup to drain any existing WAL
    database.run_checkpoint().await;

    // Build shared HTTP client
    let http_client = reqwest::Client::new();

    // Build services
    let storage = StorageService::new(&settings, http_client.clone())
        .expect("Failed to initialize storage service");

    let gemini = AiClient::gemini(
        http_client.clone(),
        &settings.gemini_api_key,
        &settings.gemini_model,
        settings.gemini_max_tokens,
        settings.gemini_temperature,
        settings.gemini_timeout,
    );

    let openrouter = AiClient::openrouter(
        http_client.clone(),
        &settings.openrouter_api_key,
        &settings.openrouter_model,
        settings.openrouter_max_tokens,
        settings.openrouter_temperature,
        settings.openrouter_timeout,
    );

    let replicate = ReplicateClient::new(
        http_client.clone(),
        &settings.replicate_api_token,
        &settings.replicate_model,
    );

    let push_notifications = PushNotificationService::new(
        http_client.clone(),
        &settings.metadata_url,
        settings.metadata_auth_token.clone(),
    );

    let ws_manager = Arc::new(WsManager::new());

    // Build app state
    let state = Arc::new(AppState {
        db: database,
        settings: settings.clone(),
        start_time: Instant::now(),
        http_client: http_client.clone(),
        storage,
        gemini,
        openrouter,
        replicate,
        push_notifications,
        ws_manager,
    });

    // Start periodic WAL checkpoint (every 5 minutes)
    Database::spawn_periodic_checkpoint(state.db.pool.clone(), 300);

    // Build CORS layer
    let cors = build_cors(&settings);

    // Build router
    use axum::routing::{delete, get, patch, post};
    use routes::{chat, chat_v2, health, influencers, media, websocket};

    let app = Router::new()
        // Health
        .route("/", get(health::root))
        .route("/health", get(health::health))
        .route("/status", get(health::status))
        // Influencers
        .route("/api/v1/influencers", get(influencers::list_influencers))
        .route(
            "/api/v1/influencers/trending",
            get(influencers::list_trending),
        )
        .route(
            "/api/v1/influencers/generate-prompt",
            post(influencers::generate_prompt),
        )
        .route(
            "/api/v1/influencers/validate-and-generate-metadata",
            post(influencers::validate_and_generate_metadata),
        )
        .route(
            "/api/v1/influencers/create",
            post(influencers::create_influencer),
        )
        .route(
            "/api/v1/influencers/{influencer_id}",
            get(influencers::get_influencer).delete(influencers::delete_influencer),
        )
        .route(
            "/api/v1/influencers/{influencer_id}/system-prompt",
            patch(influencers::update_system_prompt),
        )
        // Chat V1
        .route(
            "/api/v1/chat/conversations",
            post(chat::create_conversation).get(chat::list_conversations),
        )
        .route(
            "/api/v1/chat/conversations/{conversation_id}/messages",
            get(chat::list_messages).post(chat::send_message),
        )
        .route(
            "/api/v1/chat/conversations/{conversation_id}",
            delete(chat::delete_conversation),
        )
        .route(
            "/api/v1/chat/conversations/{conversation_id}/read",
            post(chat::mark_as_read),
        )
        .route(
            "/api/v1/chat/conversations/{conversation_id}/images",
            post(chat::generate_image),
        )
        // Chat V2
        .route(
            "/api/v2/chat/conversations",
            get(chat_v2::list_conversations_v2),
        )
        // WebSocket
        .route("/api/v1/chat/ws/inbox/{user_id}", get(websocket::ws_inbox))
        .route("/api/v1/chat/ws/docs", get(websocket::ws_docs))
        // Media
        .route("/api/v1/media/upload", post(media::upload_media))
        .layer(middleware::RateLimitLayer::new(
            settings.rate_limit_per_minute,
            settings.rate_limit_per_hour,
        ))
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

    axum::serve(listener, app).await.expect("Server error");
}

fn init_tracing(settings: &Settings) {
    use tracing_subscriber::{EnvFilter, fmt};

    let filter =
        EnvFilter::try_from_default_env().unwrap_or_else(|_| EnvFilter::new(&settings.log_level));

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
        fmt().with_env_filter(filter).with_target(true).init();
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
        let allowed: Vec<_> = origins.iter().filter_map(|o| o.parse().ok()).collect();
        use axum::http::Method;
        CorsLayer::new()
            .allow_origin(allowed)
            .allow_methods([
                Method::GET,
                Method::POST,
                Method::PUT,
                Method::PATCH,
                Method::DELETE,
                Method::OPTIONS,
            ])
            .allow_headers([
                header::AUTHORIZATION,
                header::CONTENT_TYPE,
                header::ACCEPT,
                header::ORIGIN,
                header::HeaderName::from_static("x-requested-with"),
            ])
            .allow_credentials(true)
    }
}
