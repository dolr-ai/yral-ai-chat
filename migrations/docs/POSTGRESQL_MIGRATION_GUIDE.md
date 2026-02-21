# PostgreSQL Migration Guide

This guide provides step-by-step instructions for migrating from SQLite to PostgreSQL while preserving original string IDs.

## Prerequisites

- PostgreSQL server accessible from your application
- Python environment with required dependencies
- SQLite database file accessible

## Migration Scripts Overview

All scripts are located in `migrations/scripts/` directory:

1. **`dump_sqlite_schema_to_pg.py`** - Generates PostgreSQL schema from SQLite
2. **`reset_and_apply_schema.py`** - Drops tables and applies schema
3. **`migrate_sqlite_to_postgres.py`** - Migrates data from SQLite to PostgreSQL
4. **`verify_migration.py`** - Verifies migration success

---

## Step-by-Step Migration Process

### 1. Set Up PostgreSQL Database

Create a new PostgreSQL database:

```sql
CREATE DATABASE yral_chat_production;
CREATE USER yral_chat_user WITH PASSWORD 'your_secure_password';
GRANT ALL PRIVILEGES ON DATABASE yral_chat_production TO yral_chat_user;
```

### 2. Configure Environment Variables

Set these environment variables (or add to `.env`):

```bash
export DATABASE_TYPE=postgresql
export POSTGRES_HOST=your_postgres_host
export POSTGRES_PORT=5432
export POSTGRES_USER=yral_chat_user
export POSTGRES_PASSWORD=your_secure_password
export POSTGRES_DATABASE=yral_chat_production
```

### 3. Generate PostgreSQL Schema from SQLite

This ensures the PostgreSQL schema matches your current SQLite database exactly:

```bash
python3 migrations/scripts/dump_sqlite_schema_to_pg.py
```

**Output:** `migrations/postgresql/SCHEMA_FROM_SQLITE.sql`

**What it does:**
- Inspects your SQLite database structure
- Maps SQLite types to PostgreSQL equivalents
- Preserves TEXT IDs (no UUID conversion)
- Handles JSON columns as JSONB
- Converts timestamps to TIMESTAMP WITH TIME ZONE

### 4. Apply Schema to PostgreSQL

```bash
python3 migrations/scripts/reset_and_apply_schema.py
```

**What it does:**
- Drops existing tables (if any)
- Creates tables from `SCHEMA_FROM_SQLITE.sql`
- Applies dashboard views from `004_dashboard_views.sql`

### 5. Migrate Data

```bash
python3 migrations/scripts/migrate_sqlite_to_postgres.py
```

**What it does:**
- Migrates all influencers with original string IDs
- Migrates conversations (preserving foreign keys)
- Migrates messages (preserving foreign keys)
- Uses `ON CONFLICT DO UPDATE` for idempotency

**Expected output:**
```
INFO - Migrating Influencers...
INFO - Found X influencers to migrate.
INFO - Influencers migration complete.
INFO - Migrating Conversations...
INFO - Found Y conversations to migrate.
INFO - Conversations migration complete.
INFO - Migrating Messages...
INFO - Found Z messages to migrate.
INFO - Messages migration complete.
INFO - Migration finished successfully!
```

### 6. Verify Migration

```bash
python3 migrations/scripts/verify_migration.py
```

**What it checks:**
- Row counts match between SQLite and PostgreSQL
- Sample records can be found by their original IDs
- Data integrity is maintained

**Expected output:**
```
INFO - Table ai_influencers: SQLite=X, Postgres=X
INFO - MATCH in table ai_influencers.
INFO - Table conversations: SQLite=Y, Postgres=Y
INFO - MATCH in table conversations.
INFO - Table messages: SQLite=Z, Postgres=Z
INFO - MATCH in table messages.
```

---

## Complete Migration Command (One-Liner)

For a fresh migration, run all steps sequentially:

```bash
export DATABASE_TYPE=postgresql && \
export POSTGRES_HOST=your_postgres_host && \
export POSTGRES_PORT=5432 && \
export POSTGRES_USER=yral_chat_user && \
export POSTGRES_PASSWORD=your_password && \
export POSTGRES_DATABASE=yral_chat_production && \
python3 migrations/scripts/dump_sqlite_schema_to_pg.py && \
python3 migrations/scripts/reset_and_apply_schema.py && \
python3 migrations/scripts/migrate_sqlite_to_postgres.py && \
python3 migrations/scripts/verify_migration.py
```

---

## Configuration Files to Update

### 1. Update `.env` or Environment Variables

```env
DATABASE_TYPE=postgresql
POSTGRES_HOST=your_postgres_host
POSTGRES_PORT=5432
POSTGRES_USER=yral_chat_user
POSTGRES_PASSWORD=your_secure_password
POSTGRES_DATABASE=yral_chat_production
```

### 2. Update `docker-compose.yml` (if using Docker)

Remove SQLite volume mount and ensure PostgreSQL environment variables are set:

```yaml
services:
  app:
    environment:
      - DATABASE_TYPE=postgresql
      - POSTGRES_HOST=${POSTGRES_HOST}
      - POSTGRES_PORT=${POSTGRES_PORT}
      - POSTGRES_USER=${POSTGRES_USER}
      - POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
      - POSTGRES_DATABASE=${POSTGRES_DATABASE}
    # Remove SQLite volume if present
    # volumes:
    #   - ./data:/app/data
```

---

## Rollback Plan

If you need to rollback to SQLite:

1. **Keep your SQLite database file** - Don't delete it until you're confident in PostgreSQL
2. **Change environment variable:**
   ```bash
   export DATABASE_TYPE=sqlite
   ```
3. **Restart application** - It will reconnect to SQLite

---

## Production Migration Checklist

- [ ] **Backup SQLite database**
  ```bash
  cp data/yral_chat_production.db data/yral_chat_production.db.backup
  ```

- [ ] **Create PostgreSQL database** (see Step 1)

- [ ] **Test connection to PostgreSQL**
  ```bash
  psql -h your_postgres_host -U yral_chat_user -d yral_chat_production
  ```

- [ ] **Set environment variables** (see Step 2)

- [ ] **Generate schema from SQLite**
  ```bash
  python3 migrations/scripts/dump_sqlite_schema_to_pg.py
  ```

- [ ] **Review generated schema**
  ```bash
  cat migrations/postgresql/SCHEMA_FROM_SQLITE.sql
  ```

- [ ] **Apply schema to PostgreSQL**
  ```bash
  python3 migrations/scripts/reset_and_apply_schema.py
  ```

- [ ] **Migrate data**
  ```bash
  python3 migrations/scripts/migrate_sqlite_to_postgres.py
  ```

- [ ] **Verify migration**
  ```bash
  python3 migrations/scripts/verify_migration.py
  ```

- [ ] **Update application configuration** (`.env` or environment variables)

- [ ] **Test application with PostgreSQL**
  - Start application
  - Test API endpoints
  - Verify data retrieval works

- [ ] **Monitor for issues** (first 24-48 hours)

- [ ] **Keep SQLite backup** (for at least 1 week)

---

## Troubleshooting

### Issue: "column does not exist"

**Cause:** Migration script references a column not in the generated schema.

**Fix:** Re-run schema generation to ensure it matches your current SQLite database:
```bash
python3 migrations/scripts/dump_sqlite_schema_to_pg.py
python3 migrations/scripts/reset_and_apply_schema.py
```

### Issue: Row count mismatch

**Cause:** Migration may have failed partway through.

**Fix:** Re-run migration (it's idempotent):
```bash
python3 migrations/scripts/migrate_sqlite_to_postgres.py
python3 migrations/scripts/verify_migration.py
```

### Issue: Foreign key violations

**Cause:** Data references don't exist (e.g., conversation references non-existent influencer).

**Fix:** Check migration logs for warnings about skipped records. Ensure influencers are migrated before conversations.

### Issue: Connection refused

**Cause:** PostgreSQL not accessible or wrong credentials.

**Fix:** 
1. Verify PostgreSQL is running
2. Check firewall rules
3. Verify credentials with `psql` command
4. Check `POSTGRES_HOST` and `POSTGRES_PORT` values

---

## Key Points

✅ **Original IDs Preserved** - All string IDs from SQLite are maintained  
✅ **Idempotent Scripts** - Safe to re-run if migration fails partway  
✅ **Schema Auto-Generated** - No manual schema maintenance needed  
✅ **Zero Downtime Option** - Migrate to PostgreSQL, test, then switch traffic  
✅ **Rollback Ready** - Keep SQLite backup for quick rollback if needed

---

## Files Modified/Created

### New Scripts
- `migrations/scripts/dump_sqlite_schema_to_pg.py`
- `migrations/scripts/reset_and_apply_schema.py`
- `migrations/scripts/migrate_sqlite_to_postgres.py`
- `migrations/scripts/verify_migration.py`

### Generated Files
- `migrations/postgresql/SCHEMA_FROM_SQLITE.sql` (auto-generated, don't edit manually)

### Configuration Files
- `.env` (update DATABASE_TYPE and POSTGRES_* variables)
- `docker-compose.yml` or `docker-compose.production.yml` (update environment variables)

---

## Support

If you encounter issues during production migration:

1. Check migration logs for specific error messages
2. Verify all environment variables are set correctly
3. Ensure PostgreSQL server is accessible
4. Review the troubleshooting section above
5. Keep SQLite backup until confident in PostgreSQL migration
