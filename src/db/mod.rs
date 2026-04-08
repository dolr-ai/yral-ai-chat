pub mod pg_write;
pub mod repositories;

use std::path::Path;
use std::time::Instant;

#[cfg(feature = "staging")]
use sqlx::migrate::Migrator;
#[cfg(feature = "staging")]
use sqlx::sqlite::{SqliteConnectOptions, SqlitePoolOptions};
#[cfg(feature = "staging")]
use sqlx::{ConnectOptions, SqlitePool};

#[cfg(not(feature = "staging"))]
use sqlx::migrate::Migrator;
#[cfg(not(feature = "staging"))]
use sqlx::postgres::{PgConnectOptions, PgPoolOptions};
#[cfg(not(feature = "staging"))]
use sqlx::{ConnectOptions, PgPool};

use crate::config::Settings;

pub struct HealthCheckResult {
    pub status: String,
    pub latency_ms: Option<i64>,
    pub error: Option<String>,
    pub size_mb: f64,
}

// ── Staging: SQLite-only ──────────────────────────────────────────────────────

#[cfg(feature = "staging")]
#[derive(Clone)]
pub struct Database {
    pub pool: SqlitePool,
    pub db_path: String,
}

#[cfg(feature = "staging")]
impl Database {
    pub async fn connect(settings: &Settings) -> Result<Self, sqlx::Error> {
        let db_path = resolve_db_path(&settings.database_path);

        if let Some(parent) = Path::new(&db_path).parent() {
            std::fs::create_dir_all(parent).ok();
        }

        let connect_options = SqliteConnectOptions::new()
            .filename(&db_path)
            .create_if_missing(true)
            .journal_mode(sqlx::sqlite::SqliteJournalMode::Wal)
            .synchronous(sqlx::sqlite::SqliteSynchronous::Normal)
            .busy_timeout(std::time::Duration::from_secs(
                settings.database_pool_timeout,
            ))
            .pragma("foreign_keys", "ON")
            .pragma("wal_autocheckpoint", "0")
            .pragma("journal_size_limit", "67108864")
            .pragma("mmap_size", "33554432")
            .pragma("cache_size", "-16000")
            .pragma("temp_store", "MEMORY")
            .disable_statement_logging();

        let pool = SqlitePoolOptions::new()
            .max_connections(settings.database_pool_size)
            .acquire_timeout(std::time::Duration::from_secs(
                settings.database_pool_timeout,
            ))
            .connect_with(connect_options)
            .await?;

        let version: (String,) = sqlx::query_as("SELECT sqlite_version()")
            .fetch_one(&pool)
            .await?;
        tracing::info!(
            sqlite_version = %version.0,
            path = %db_path,
            pool_size = settings.database_pool_size,
            "Connected to SQLite database"
        );

        Ok(Self { pool, db_path })
    }

    pub fn conv_repo(&self) -> repositories::ConversationRepository {
        repositories::ConversationRepository::new(self.pool.clone())
    }

    pub fn msg_repo(&self) -> repositories::MessageRepository {
        repositories::MessageRepository::new(self.pool.clone())
    }

    pub fn inf_repo(&self) -> repositories::InfluencerRepository {
        repositories::InfluencerRepository::new(self.pool.clone())
    }

    pub async fn run_checkpoint(&self) {
        match sqlx::query_as::<_, (i32, i32, i32)>("PRAGMA wal_checkpoint(PASSIVE)")
            .fetch_one(&self.pool)
            .await
        {
            Ok((busy, log, checkpointed)) => {
                tracing::info!(
                    busy,
                    log_pages = log,
                    checkpointed_pages = checkpointed,
                    "WAL checkpoint completed"
                );
            }
            Err(e) => tracing::warn!(error = %e, "WAL checkpoint failed (non-fatal)"),
        }
    }

    pub fn spawn_periodic_checkpoint(pool: SqlitePool, interval_secs: u64) {
        tokio::spawn(async move {
            let interval = std::time::Duration::from_secs(interval_secs);
            loop {
                tokio::time::sleep(interval).await;
                match sqlx::query_as::<_, (i32, i32, i32)>("PRAGMA wal_checkpoint(PASSIVE)")
                    .fetch_one(&pool)
                    .await
                {
                    Ok((busy, log, checkpointed)) => {
                        tracing::info!(
                            busy,
                            log_pages = log,
                            checkpointed_pages = checkpointed,
                            "Periodic WAL checkpoint completed"
                        );
                    }
                    Err(e) => {
                        tracing::warn!(error = %e, "Periodic WAL checkpoint failed (non-fatal)")
                    }
                }
            }
        });
    }

    pub async fn health_check(&self) -> HealthCheckResult {
        let start = Instant::now();
        match sqlx::query_scalar::<_, i32>("SELECT 1")
            .fetch_one(&self.pool)
            .await
        {
            Ok(_) => {
                let latency_ms = start.elapsed().as_millis() as i64;
                let size_mb = Path::new(&self.db_path)
                    .metadata()
                    .map(|m| m.len() as f64 / (1024.0 * 1024.0))
                    .unwrap_or(0.0);
                HealthCheckResult {
                    status: "up".to_string(),
                    latency_ms: Some(latency_ms),
                    error: None,
                    size_mb,
                }
            }
            Err(e) => HealthCheckResult {
                status: "down".to_string(),
                latency_ms: None,
                error: Some(e.to_string()),
                size_mb: 0.0,
            },
        }
    }

    pub async fn pg_health_check(&self) -> Option<HealthCheckResult> {
        None
    }
}

// ── Non-staging: PostgreSQL-only ──────────────────────────────────────────────

#[cfg(not(feature = "staging"))]
#[derive(Clone)]
pub struct Database {
    pub pg_pool: PgPool,
    pub primary_pg_pool: Option<PgPool>,
}

#[cfg(not(feature = "staging"))]
impl Database {
    pub async fn connect(settings: &Settings) -> Result<Self, sqlx::Error> {
        let pg_url = settings
            .pg_database_url
            .as_deref()
            .expect("PG_DATABASE_URL is required for non-staging builds");

        let connect_options: PgConnectOptions = pg_url
            .parse::<PgConnectOptions>()?
            .disable_statement_logging();

        let pg_pool = PgPoolOptions::new()
            .max_connections(settings.pg_pool_size)
            .acquire_timeout(std::time::Duration::from_secs(settings.pg_pool_timeout))
            .connect_with(connect_options)
            .await?;

        sqlx::query_scalar::<_, i32>("SELECT 1")
            .fetch_one(&pg_pool)
            .await?;

        tracing::info!(pool_size = settings.pg_pool_size, "Connected to PostgreSQL");

        let primary_pg_pool = match &settings.primary_pg_database_url {
            Some(url) => {
                let opts = url
                    .parse::<PgConnectOptions>()
                    .map(|o| o.disable_statement_logging());
                match opts {
                    Ok(opts) => {
                        match PgPoolOptions::new()
                            .max_connections(settings.pg_pool_size)
                            .acquire_timeout(std::time::Duration::from_secs(
                                settings.pg_pool_timeout,
                            ))
                            .connect_with(opts)
                            .await
                        {
                            Ok(pool) => {
                                tracing::info!("Connected to primary PostgreSQL for dual-write");
                                Some(pool)
                            }
                            Err(e) => {
                                tracing::warn!(
                                    error = %e,
                                    "Failed to connect to primary PostgreSQL, dual-write disabled"
                                );
                                None
                            }
                        }
                    }
                    Err(e) => {
                        tracing::warn!(
                            error = %e,
                            "Invalid PRIMARY_PG_DATABASE_URL, dual-write disabled"
                        );
                        None
                    }
                }
            }
            None => {
                tracing::info!("PRIMARY_PG_DATABASE_URL not set, dual-write disabled");
                None
            }
        };

        Ok(Self {
            pg_pool,
            primary_pg_pool,
        })
    }

    pub fn conv_repo(&self) -> repositories::ConversationRepository {
        repositories::ConversationRepository::new(
            self.pg_pool.clone(),
            self.primary_pg_pool.clone(),
        )
    }

    pub fn msg_repo(&self) -> repositories::MessageRepository {
        repositories::MessageRepository::new(self.pg_pool.clone(), self.primary_pg_pool.clone())
    }

    pub fn inf_repo(&self) -> repositories::InfluencerRepository {
        repositories::InfluencerRepository::new(self.pg_pool.clone(), self.primary_pg_pool.clone())
    }

    pub async fn health_check(&self) -> HealthCheckResult {
        let start = Instant::now();
        match sqlx::query_scalar::<_, i32>("SELECT 1")
            .fetch_one(&self.pg_pool)
            .await
        {
            Ok(_) => HealthCheckResult {
                status: "up".to_string(),
                latency_ms: Some(start.elapsed().as_millis() as i64),
                error: None,
                size_mb: 0.0,
            },
            Err(e) => HealthCheckResult {
                status: "down".to_string(),
                latency_ms: None,
                error: Some(e.to_string()),
                size_mb: 0.0,
            },
        }
    }

    pub async fn pg_health_check(&self) -> Option<HealthCheckResult> {
        Some(self.health_check().await)
    }

    pub async fn primary_pg_health_check(&self) -> Option<HealthCheckResult> {
        let pool = self.primary_pg_pool.as_ref()?;
        let start = Instant::now();
        match sqlx::query_scalar::<_, i32>("SELECT 1")
            .fetch_one(pool)
            .await
        {
            Ok(_) => Some(HealthCheckResult {
                status: "up".to_string(),
                latency_ms: Some(start.elapsed().as_millis() as i64),
                error: None,
                size_mb: 0.0,
            }),
            Err(e) => Some(HealthCheckResult {
                status: "down".to_string(),
                latency_ms: None,
                error: Some(e.to_string()),
                size_mb: 0.0,
            }),
        }
    }
}

// ── Migrations ────────────────────────────────────────────────────────────────

#[cfg(feature = "staging")]
pub async fn run_migrations(pool: &SqlitePool, migrations_dir: &str) -> Result<(), sqlx::Error> {
    let path = Path::new(migrations_dir);
    if !path.exists() {
        tracing::warn!(path = %migrations_dir, "Migrations directory not found, skipping");
        return Ok(());
    }
    let migrator = Migrator::new(path).await?;
    migrator.run(pool).await?;
    tracing::info!("SQLite migrations applied successfully");
    Ok(())
}

#[cfg(not(feature = "staging"))]
pub async fn run_pg_migrations(pool: &PgPool, migrations_dir: &str) -> Result<(), sqlx::Error> {
    let path = Path::new(migrations_dir);
    if !path.exists() {
        tracing::warn!(path = %migrations_dir, "PG migrations directory not found, skipping");
        return Ok(());
    }
    let migrator = Migrator::new(path).await?;
    migrator.run(pool).await?;
    tracing::info!("PostgreSQL migrations applied successfully");
    Ok(())
}

// ── Helpers ───────────────────────────────────────────────────────────────────

#[cfg(feature = "staging")]
fn resolve_db_path(db_path: &str) -> String {
    let path = Path::new(db_path);
    if path.is_absolute() {
        return db_path.to_string();
    }
    let base = if Path::new("/app/migrations").exists() {
        Path::new("/app").to_path_buf()
    } else {
        std::env::current_dir().unwrap_or_else(|_| Path::new(".").to_path_buf())
    };
    base.join(db_path).to_string_lossy().into_owned()
}
