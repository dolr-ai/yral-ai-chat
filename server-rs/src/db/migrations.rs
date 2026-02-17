use sqlx::migrate::Migrator;
use sqlx::SqlitePool;
use std::path::Path;

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
