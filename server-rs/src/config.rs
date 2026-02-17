use std::env;

#[derive(Debug, Clone)]
pub struct Settings {
    // App
    pub app_name: String,
    pub app_version: String,
    pub environment: Environment,
    pub debug: bool,
    pub host: String,
    pub port: u16,

    // Database
    pub database_path: String,
    pub database_pool_size: u32,
    pub database_pool_timeout: u64,

    // JWT
    pub jwt_secret_key: String,
    pub jwt_algorithm: String,
    pub jwt_issuer: String,

    // Gemini
    pub gemini_api_key: String,
    pub gemini_model: String,
    pub gemini_max_tokens: u32,
    pub gemini_temperature: f32,
    pub gemini_timeout: u64,

    // OpenRouter
    pub openrouter_api_key: String,
    pub openrouter_model: String,
    pub openrouter_max_tokens: u32,
    pub openrouter_temperature: f32,
    pub openrouter_timeout: u64,

    // Media limits
    pub max_image_size_mb: u32,
    pub max_audio_size_mb: u32,
    pub max_audio_duration_seconds: u32,

    // S3
    pub aws_access_key_id: String,
    pub aws_secret_access_key: String,
    pub aws_s3_bucket: String,
    pub aws_region: String,
    pub s3_endpoint_url: String,
    pub s3_public_url_base: String,
    pub s3_url_expires_seconds: u32,

    // CORS
    pub cors_origins: String,

    // Rate limiting
    pub rate_limit_per_minute: u32,
    pub rate_limit_per_hour: u32,

    // Logging
    pub log_level: String,
    pub log_format: String,

    // Sentry
    pub sentry_dsn: Option<String>,
    pub sentry_traces_sample_rate: f64,
    pub sentry_profiles_sample_rate: f64,
    pub sentry_webhook_secret: Option<String>,

    // Notifications
    pub google_chat_webhook_url: Option<String>,
}

#[derive(Debug, Clone, PartialEq)]
pub enum Environment {
    Development,
    Staging,
    Production,
}

impl Environment {
    fn from_str(s: &str) -> Self {
        match s.to_lowercase().as_str() {
            "production" => Self::Production,
            "staging" => Self::Staging,
            _ => Self::Development,
        }
    }

    pub fn as_str(&self) -> &str {
        match self {
            Self::Development => "development",
            Self::Staging => "staging",
            Self::Production => "production",
        }
    }
}

impl Settings {
    pub fn from_env() -> Self {
        Self {
            app_name: env_or("APP_NAME", "Yral AI Chat API"),
            app_version: env_or("APP_VERSION", "1.0.0"),
            environment: Environment::from_str(&env_or("ENVIRONMENT", "development")),
            debug: env_or("DEBUG", "false").parse().unwrap_or(false),
            host: env_or("HOST", "0.0.0.0"),
            port: env_or("PORT", "8000").parse().unwrap_or(8000),

            database_path: env_or("DATABASE_PATH", "data/yral_chat.db"),
            database_pool_size: env_or("DATABASE_POOL_SIZE", "10")
                .parse()
                .unwrap_or(10),
            database_pool_timeout: env_or("DATABASE_POOL_TIMEOUT", "60")
                .parse()
                .unwrap_or(60),

            jwt_secret_key: env_required("JWT_SECRET_KEY"),
            jwt_algorithm: env_or("JWT_ALGORITHM", "HS256"),
            jwt_issuer: env_or("JWT_ISSUER", "yral_auth"),

            gemini_api_key: env_required("GEMINI_API_KEY"),
            gemini_model: env_or("GEMINI_MODEL", "gemini-2.5-flash"),
            gemini_max_tokens: env_or("GEMINI_MAX_TOKENS", "2048")
                .parse()
                .unwrap_or(2048),
            gemini_temperature: env_or("GEMINI_TEMPERATURE", "0.7")
                .parse()
                .unwrap_or(0.7),
            gemini_timeout: env_or("GEMINI_TIMEOUT", "60").parse().unwrap_or(60),

            openrouter_api_key: env_or("OPENROUTER_API_KEY", ""),
            openrouter_model: env_or("OPENROUTER_MODEL", "google/gemini-2.5-flash"),
            openrouter_max_tokens: env_or("OPENROUTER_MAX_TOKENS", "2048")
                .parse()
                .unwrap_or(2048),
            openrouter_temperature: env_or("OPENROUTER_TEMPERATURE", "0.7")
                .parse()
                .unwrap_or(0.7),
            openrouter_timeout: env_or("OPENROUTER_TIMEOUT", "30")
                .parse()
                .unwrap_or(30),

            max_image_size_mb: env_or("MAX_IMAGE_SIZE_MB", "10")
                .parse()
                .unwrap_or(10),
            max_audio_size_mb: env_or("MAX_AUDIO_SIZE_MB", "20")
                .parse()
                .unwrap_or(20),
            max_audio_duration_seconds: env_or("MAX_AUDIO_DURATION_SECONDS", "300")
                .parse()
                .unwrap_or(300),

            aws_access_key_id: env_required("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key: env_required("AWS_SECRET_ACCESS_KEY"),
            aws_s3_bucket: env_required("AWS_S3_BUCKET"),
            aws_region: env_required("AWS_REGION"),
            s3_endpoint_url: env_required("S3_ENDPOINT_URL"),
            s3_public_url_base: env_required("S3_PUBLIC_URL_BASE"),
            s3_url_expires_seconds: env_or("S3_URL_EXPIRES_SECONDS", "900")
                .parse()
                .unwrap_or(900),

            cors_origins: env_or("CORS_ORIGINS", "*"),

            rate_limit_per_minute: env_or("RATE_LIMIT_PER_MINUTE", "300")
                .parse()
                .unwrap_or(300),
            rate_limit_per_hour: env_or("RATE_LIMIT_PER_HOUR", "5000")
                .parse()
                .unwrap_or(5000),

            log_level: env_or("LOG_LEVEL", "info"),
            log_format: env_or("LOG_FORMAT", "json"),

            sentry_dsn: env::var("SENTRY_DSN").ok().filter(|s| !s.is_empty()),
            sentry_traces_sample_rate: env_or("SENTRY_TRACES_SAMPLE_RATE", "1.0")
                .parse()
                .unwrap_or(1.0),
            sentry_profiles_sample_rate: env_or("SENTRY_PROFILES_SAMPLE_RATE", "1.0")
                .parse()
                .unwrap_or(1.0),
            sentry_webhook_secret: env::var("SENTRY_WEBHOOK_SECRET")
                .ok()
                .filter(|s| !s.is_empty()),

            google_chat_webhook_url: env::var("GOOGLE_CHAT")
                .ok()
                .filter(|s| !s.is_empty()),
        }
    }

    pub fn cors_origins_list(&self) -> Vec<String> {
        if self.cors_origins == "*" {
            return vec!["*".to_string()];
        }
        self.cors_origins
            .split(',')
            .map(|s| s.trim().to_string())
            .collect()
    }

    pub fn max_image_size_bytes(&self) -> u64 {
        self.max_image_size_mb as u64 * 1024 * 1024
    }

    pub fn max_audio_size_bytes(&self) -> u64 {
        self.max_audio_size_mb as u64 * 1024 * 1024
    }
}

fn env_or(key: &str, default: &str) -> String {
    env::var(key).unwrap_or_else(|_| default.to_string())
}

fn env_required(key: &str) -> String {
    env::var(key).unwrap_or_else(|_| {
        tracing::warn!("{key} not set, using empty string");
        String::new()
    })
}
