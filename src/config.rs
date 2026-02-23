use std::env;

#[derive(Debug, Clone)]
pub struct Settings {
    // App
    pub app_name: String,
    pub app_version: String,
    pub environment: String,
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

    // Replicate (Image Generation)
    pub replicate_api_token: String,
    pub replicate_model: String,

    // Push Notifications (Metadata Server)
    pub metadata_url: String,
    pub metadata_auth_token: Option<String>,

    // Sentry
    pub sentry_dsn: Option<String>,
    pub sentry_traces_sample_rate: f64,
    pub sentry_profiles_sample_rate: f64,
    pub sentry_webhook_secret: Option<String>,

    // Notifications
    pub google_chat_webhook_url: Option<String>,
}

impl Settings {
    pub fn from_env() -> Self {
        Self {
            app_name: env::var("APP_NAME").unwrap_or("Yral AI Chat API".into()),
            app_version: env::var("APP_VERSION").unwrap_or("1.0.0".into()),
            environment: env::var("ENVIRONMENT").unwrap_or("development".into()),
            debug: env::var("DEBUG")
                .unwrap_or("false".into())
                .parse()
                .unwrap_or(false),
            host: env::var("HOST").unwrap_or("0.0.0.0".into()),
            port: env::var("PORT")
                .unwrap_or("8000".into())
                .parse()
                .unwrap_or(8000),

            database_path: env::var("DATABASE_PATH").unwrap_or("data/yral_chat.db".into()),
            database_pool_size: env::var("DATABASE_POOL_SIZE")
                .unwrap_or("10".into())
                .parse()
                .unwrap_or(10),
            database_pool_timeout: env::var("DATABASE_POOL_TIMEOUT")
                .unwrap_or("60".into())
                .parse()
                .unwrap_or(60),

            jwt_secret_key: env::var("JWT_SECRET_KEY").expect("JWT_SECRET_KEY is required"),
            jwt_algorithm: env::var("JWT_ALGORITHM").unwrap_or("HS256".into()),
            jwt_issuer: env::var("JWT_ISSUER").unwrap_or("yral_auth".into()),

            gemini_api_key: env::var("GEMINI_API_KEY").expect("GEMINI_API_KEY is required"),
            gemini_model: env::var("GEMINI_MODEL").unwrap_or("gemini-2.5-flash".into()),
            gemini_max_tokens: env::var("GEMINI_MAX_TOKENS")
                .unwrap_or("2048".into())
                .parse()
                .unwrap_or(2048),
            gemini_temperature: env::var("GEMINI_TEMPERATURE")
                .unwrap_or("0.7".into())
                .parse()
                .unwrap_or(0.7),
            gemini_timeout: env::var("GEMINI_TIMEOUT")
                .unwrap_or("60".into())
                .parse()
                .unwrap_or(60),

            openrouter_api_key: env::var("OPENROUTER_API_KEY").unwrap_or_default(),
            openrouter_model: env::var("OPENROUTER_MODEL")
                .unwrap_or("google/gemini-2.5-flash".into()),
            openrouter_max_tokens: env::var("OPENROUTER_MAX_TOKENS")
                .unwrap_or("2048".into())
                .parse()
                .unwrap_or(2048),
            openrouter_temperature: env::var("OPENROUTER_TEMPERATURE")
                .unwrap_or("0.7".into())
                .parse()
                .unwrap_or(0.7),
            openrouter_timeout: env::var("OPENROUTER_TIMEOUT")
                .unwrap_or("30".into())
                .parse()
                .unwrap_or(30),

            max_image_size_mb: env::var("MAX_IMAGE_SIZE_MB")
                .unwrap_or("10".into())
                .parse()
                .unwrap_or(10),
            max_audio_size_mb: env::var("MAX_AUDIO_SIZE_MB")
                .unwrap_or("20".into())
                .parse()
                .unwrap_or(20),
            max_audio_duration_seconds: env::var("MAX_AUDIO_DURATION_SECONDS")
                .unwrap_or("300".into())
                .parse()
                .unwrap_or(300),

            aws_access_key_id: env::var("AWS_ACCESS_KEY_ID")
                .expect("AWS_ACCESS_KEY_ID is required"),
            aws_secret_access_key: env::var("AWS_SECRET_ACCESS_KEY")
                .expect("AWS_SECRET_ACCESS_KEY is required"),
            aws_s3_bucket: env::var("AWS_S3_BUCKET").expect("AWS_S3_BUCKET is required"),
            aws_region: env::var("AWS_REGION").expect("AWS_REGION is required"),
            s3_endpoint_url: env::var("S3_ENDPOINT_URL").expect("S3_ENDPOINT_URL is required"),
            s3_public_url_base: env::var("S3_PUBLIC_URL_BASE")
                .expect("S3_PUBLIC_URL_BASE is required"),
            s3_url_expires_seconds: env::var("S3_URL_EXPIRES_SECONDS")
                .unwrap_or("900".into())
                .parse()
                .unwrap_or(900),

            cors_origins: env::var("CORS_ORIGINS").unwrap_or("*".into()),

            rate_limit_per_minute: env::var("RATE_LIMIT_PER_MINUTE")
                .unwrap_or("300".into())
                .parse()
                .unwrap_or(300),
            rate_limit_per_hour: env::var("RATE_LIMIT_PER_HOUR")
                .unwrap_or("5000".into())
                .parse()
                .unwrap_or(5000),

            log_level: env::var("LOG_LEVEL").unwrap_or("info".into()),
            log_format: env::var("LOG_FORMAT").unwrap_or("json".into()),

            replicate_api_token: env::var("REPLICATE_API_TOKEN").unwrap_or_default(),
            replicate_model: env::var("REPLICATE_MODEL")
                .unwrap_or("black-forest-labs/flux-dev".into()),

            metadata_url: env::var("METADATA_URL").unwrap_or("https://metadata.yral.com".into()),
            metadata_auth_token: env::var("YRAL_METADATA_NOTIFICATION_API_KEY")
                .ok()
                .filter(|s| !s.is_empty()),

            sentry_dsn: env::var("SENTRY_DSN").ok().filter(|s| !s.is_empty()),
            sentry_traces_sample_rate: env::var("SENTRY_TRACES_SAMPLE_RATE")
                .unwrap_or("1.0".into())
                .parse()
                .unwrap_or(1.0),
            sentry_profiles_sample_rate: env::var("SENTRY_PROFILES_SAMPLE_RATE")
                .unwrap_or("1.0".into())
                .parse()
                .unwrap_or(1.0),
            sentry_webhook_secret: env::var("SENTRY_WEBHOOK_SECRET")
                .ok()
                .filter(|s| !s.is_empty()),

            google_chat_webhook_url: env::var("GOOGLE_CHAT").ok().filter(|s| !s.is_empty()),
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

    #[inline]
    pub fn max_image_size_bytes(&self) -> u64 {
        self.max_image_size_mb as u64 * 1024 * 1024
    }

    #[inline]
    pub fn max_audio_size_bytes(&self) -> u64 {
        self.max_audio_size_mb as u64 * 1024 * 1024
    }
}
