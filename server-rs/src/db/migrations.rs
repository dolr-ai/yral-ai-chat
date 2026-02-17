use sqlx::SqlitePool;
use std::path::Path;

pub async fn run_migrations(pool: &SqlitePool, migrations_dir: &str) -> Result<(), String> {
    // Ensure migrations tracking table exists
    sqlx::query(
        "CREATE TABLE IF NOT EXISTS _migrations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL UNIQUE,
            applied_at TEXT DEFAULT (datetime('now'))
        )",
    )
    .execute(pool)
    .await
    .map_err(|e| format!("Failed to create migrations table: {e}"))?;

    let dir = Path::new(migrations_dir);
    if !dir.exists() {
        tracing::warn!(path = %migrations_dir, "Migrations directory not found, skipping");
        return Ok(());
    }

    // Collect and sort migration files
    let mut files: Vec<_> = std::fs::read_dir(dir)
        .map_err(|e| format!("Failed to read migrations directory: {e}"))?
        .filter_map(|entry| {
            let entry = entry.ok()?;
            let name = entry.file_name().to_string_lossy().to_string();
            if name.ends_with(".sql") {
                Some((name, entry.path()))
            } else {
                None
            }
        })
        .collect();

    files.sort_by(|a, b| a.0.cmp(&b.0));

    for (filename, path) in &files {
        // Check if already applied
        let applied: Option<(i32,)> =
            sqlx::query_as("SELECT 1 FROM _migrations WHERE filename = ?")
                .bind(filename)
                .fetch_optional(pool)
                .await
                .map_err(|e| format!("Failed to check migration status for {filename}: {e}"))?;

        if applied.is_some() {
            tracing::debug!(filename = %filename, "Migration already applied, skipping");
            continue;
        }

        // Read and execute migration
        let sql = std::fs::read_to_string(path)
            .map_err(|e| format!("Failed to read migration {filename}: {e}"))?;

        tracing::info!(filename = %filename, "Applying migration");

        // Split by statements and execute individually
        // (SQLite doesn't support multiple statements in one execute via sqlx)
        for statement in split_sql_statements(&sql) {
            let trimmed = statement.trim();
            if trimmed.is_empty() || trimmed.starts_with("--") {
                continue;
            }
            sqlx::query(trimmed)
                .execute(pool)
                .await
                .map_err(|e| format!("Migration {filename} failed on statement: {e}\nSQL: {trimmed}"))?;
        }

        // Record migration
        sqlx::query("INSERT INTO _migrations (filename) VALUES (?)")
            .bind(filename)
            .execute(pool)
            .await
            .map_err(|e| format!("Failed to record migration {filename}: {e}"))?;

        tracing::info!(filename = %filename, "Migration applied successfully");
    }

    Ok(())
}

fn split_sql_statements(sql: &str) -> Vec<String> {
    let mut statements = Vec::new();
    let mut current = String::new();
    let mut in_trigger = false;

    for line in sql.lines() {
        let trimmed = line.trim();

        // Track BEGIN/END for triggers (they contain semicolons inside)
        if trimmed.to_uppercase().contains("CREATE TRIGGER")
            || trimmed.to_uppercase().contains("BEGIN")
        {
            if trimmed.to_uppercase().contains("CREATE TRIGGER") {
                in_trigger = true;
            }
        }

        current.push_str(line);
        current.push('\n');

        if in_trigger {
            if trimmed.to_uppercase().starts_with("END;") {
                statements.push(current.clone());
                current.clear();
                in_trigger = false;
            }
        } else if trimmed.ends_with(';') {
            statements.push(current.clone());
            current.clear();
        }
    }

    // Push any remaining content
    if !current.trim().is_empty() {
        statements.push(current);
    }

    statements
}
