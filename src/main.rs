mod auth;
mod config;
mod db;
mod error;
mod models;
mod routes;
mod services;

use std::sync::Arc;
use std::time::Instant;

use axum::Router;
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
        storage,
        gemini,
        openrouter,
        replicate,
        push_notifications,
        ws_manager,
    });

    // Build CORS layer
    let cors = build_cors(&settings);

    // Build router
    let app = Router::new()
        // Health
        .route("/", axum::routing::get(routes::health::root))
        .route("/health", axum::routing::get(routes::health::health))
        .route("/status", axum::routing::get(routes::health::status))
        // Influencers
        .route(
            "/api/v1/influencers",
            axum::routing::get(routes::influencers::list_influencers),
        )
        .route(
            "/api/v1/influencers/trending",
            axum::routing::get(routes::influencers::list_trending),
        )
        .route(
            "/api/v1/influencers/generate-prompt",
            axum::routing::post(routes::influencers::generate_prompt),
        )
        .route(
            "/api/v1/influencers/validate-and-generate-metadata",
            axum::routing::post(routes::influencers::validate_and_generate_metadata),
        )
        .route(
            "/api/v1/influencers/create",
            axum::routing::post(routes::influencers::create_influencer),
        )
        .route(
            "/api/v1/influencers/{influencer_id}",
            axum::routing::get(routes::influencers::get_influencer)
                .delete(routes::influencers::delete_influencer),
        )
        .route(
            "/api/v1/influencers/{influencer_id}/system-prompt",
            axum::routing::patch(routes::influencers::update_system_prompt),
        )
        // Chat V1
        .route(
            "/api/v1/chat/conversations",
            axum::routing::post(routes::chat::create_conversation)
                .get(routes::chat::list_conversations),
        )
        .route(
            "/api/v1/chat/conversations/{conversation_id}/messages",
            axum::routing::get(routes::chat::list_messages).post(routes::chat::send_message),
        )
        .route(
            "/api/v1/chat/conversations/{conversation_id}",
            axum::routing::delete(routes::chat::delete_conversation),
        )
        .route(
            "/api/v1/chat/conversations/{conversation_id}/read",
            axum::routing::post(routes::chat::mark_as_read),
        )
        .route(
            "/api/v1/chat/conversations/{conversation_id}/images",
            axum::routing::post(routes::chat::generate_image),
        )
        // Chat V2
        .route(
            "/api/v2/chat/conversations",
            axum::routing::get(routes::chat_v2::list_conversations_v2),
        )
        // WebSocket
        .route(
            "/api/v1/chat/ws/inbox/{user_id}",
            axum::routing::get(routes::websocket::ws_inbox),
        )
        // Media
        .route(
            "/api/v1/media/upload",
            axum::routing::post(routes::media::upload_media),
        )
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
