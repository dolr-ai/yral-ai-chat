pub mod repositories;

use std::path::Path;
use std::time::Instant;

use sqlx::migrate::Migrator;
use sqlx::sqlite::{SqliteConnectOptions, SqlitePoolOptions};
use sqlx::{ConnectOptions, SqlitePool};

use crate::config::Settings;

#[derive(Clone)]
pub struct Database {
    pub pool: SqlitePool,
    pub db_path: String,
}

impl Database {
    pub async fn connect(settings: &Settings) -> Result<Self, sqlx::Error> {
        let db_path = resolve_db_path(&settings.database_path);

        // Ensure parent directory exists
        if let Some(parent) = Path::new(&db_path).parent() {
            std::fs::create_dir_all(parent).ok();
        }

        let connect_options = SqliteConnectOptions::new()
            .filename(&db_path)
            .create_if_missing(true)
            .journal_mode(sqlx::sqlite::SqliteJournalMode::Wal)
            .synchronous(sqlx::sqlite::SqliteSynchronous::Normal)
            .busy_timeout(std::time::Duration::from_secs(settings.database_pool_timeout))
            .pragma("foreign_keys", "ON")
            // CRITICAL: Disable autocheckpoint. Litestream holds continuous read locks
            // on the WAL during replication; SQLite's TRUNCATE checkpoint requires ZERO
            // active readers. With pool connections + Litestream, autocheckpoint silently
            // fails, causing unbounded WAL growth (600MB+).
            .pragma("wal_autocheckpoint", "0")
            .pragma("journal_size_limit", "67108864")
            // Reduced from 256MB to 32MB: the 256MB mmap per connection multiplied
            // across pool connections was a major OOM contributor.
            .pragma("mmap_size", "33554432")
            // Reduced from 64MB to 16MB for the same OOM reason.
            .pragma("cache_size", "-16000")
            .pragma("temp_store", "MEMORY")
            .disable_statement_logging();

        let pool = SqlitePoolOptions::new()
            .max_connections(settings.database_pool_size)
            .acquire_timeout(std::time::Duration::from_secs(settings.database_pool_timeout))
            .connect_with(connect_options)
            .await?;

        let db = Self {
            pool,
            db_path: db_path.clone(),
        };

        // Verify connection
        let version: (String,) = sqlx::query_as("SELECT sqlite_version()")
            .fetch_one(&db.pool)
            .await?;
        tracing::info!(
            sqlite_version = %version.0,
            path = %db_path,
            pool_size = settings.database_pool_size,
            "Connected to SQLite database"
        );

        Ok(db)
    }

    /// Run an immediate PASSIVE WAL checkpoint (e.g., on startup to drain existing WAL).
    pub async fn run_checkpoint(&self) {
        match sqlx::query_as::<_, (i32, i32, i32)>("PRAGMA wal_checkpoint(PASSIVE)")
            .fetch_one(&self.pool)
            .await
        {
            Ok((busy, log, checkpointed)) => {
                tracing::info!(
                    busy = busy,
                    log_pages = log,
                    checkpointed_pages = checkpointed,
                    "WAL checkpoint completed"
                );
            }
            Err(e) => {
                tracing::warn!(error = %e, "WAL checkpoint failed (non-fatal)");
            }
        }
    }

    /// Spawn a background task that runs PASSIVE WAL checkpoint every `interval_secs` seconds.
    /// Safety net for when wal_autocheckpoint=0 is set.
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
                            busy = busy,
                            log_pages = log,
                            checkpointed_pages = checkpointed,
                            "Periodic WAL checkpoint completed"
                        );
                    }
                    Err(e) => {
                        tracing::warn!(error = %e, "Periodic WAL checkpoint failed (non-fatal)");
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
}

pub struct HealthCheckResult {
    pub status: String,
    pub latency_ms: Option<i64>,
    pub error: Option<String>,
    pub size_mb: f64,
}

pub async fn run_migrations(pool: &SqlitePool, migrations_dir: &str) -> Result<(), sqlx::Error> {
    let path = Path::new(migrations_dir);

    if !path.exists() {
        tracing::warn!(path = %migrations_dir, "Migrations directory not found, skipping");
        return Ok(());
    }

    let migrator = Migrator::new(path).await?;
    migrator.run(pool).await?;

    tracing::info!("Migrations applied successfully");
    Ok(())
}

fn resolve_db_path(db_path: &str) -> String {
    let path = Path::new(db_path);
    if path.is_absolute() {
        return db_path.to_string();
    }

    // Use /app in Docker, otherwise resolve relative to cwd
    let base = if Path::new("/app/migrations").exists() {
        Path::new("/app").to_path_buf()
    } else {
        std::env::current_dir().unwrap_or_else(|_| Path::new(".").to_path_buf())
    };

    base.join(db_path)
        .to_string_lossy()
        .into_owned()
}
