# PostgreSQL Migration - Quick Reference

## TL;DR - Complete Migration in 4 Commands

```bash
# 1. Set environment variables
export DATABASE_TYPE=postgresql
export POSTGRES_HOST=your_host
export POSTGRES_PORT=5432
export POSTGRES_USER=yral_chat_user
export POSTGRES_PASSWORD=your_password
export POSTGRES_DATABASE=yral_chat_production

# 2. Generate schema from SQLite
python3 migrations/scripts/dump_sqlite_schema_to_pg.py

# 3. Apply schema and migrate data
python3 migrations/scripts/reset_and_apply_schema.py && \
python3 migrations/scripts/migrate_sqlite_to_postgres.py

# 4. Verify
python3 migrations/scripts/verify_migration.py
```

## Pre-Migration

```bash
# Backup SQLite
cp data/yral_chat_production.db data/yral_chat_production.db.backup

# Create PostgreSQL database
psql -h your_host -U postgres -c "CREATE DATABASE yral_chat_production;"
psql -h your_host -U postgres -c "CREATE USER yral_chat_user WITH PASSWORD 'password';"
psql -h your_host -U postgres -c "GRANT ALL PRIVILEGES ON DATABASE yral_chat_production TO yral_chat_user;"
```

## Post-Migration

```bash
# Update .env
echo "DATABASE_TYPE=postgresql" >> .env
echo "POSTGRES_HOST=your_host" >> .env
echo "POSTGRES_PORT=5432" >> .env
echo "POSTGRES_USER=yral_chat_user" >> .env
echo "POSTGRES_PASSWORD=your_password" >> .env
echo "POSTGRES_DATABASE=yral_chat_production" >> .env

# Restart application
docker-compose restart  # or your deployment method
```

## Rollback

```bash
# Switch back to SQLite
export DATABASE_TYPE=sqlite
# Restart application
```

## Files to Commit

```bash
git add migrations/scripts/dump_sqlite_schema_to_pg.py
git add migrations/scripts/reset_and_apply_schema.py
git add migrations/scripts/migrate_sqlite_to_postgres.py
git add migrations/scripts/verify_migration.py
git add migrations/docs/POSTGRESQL_MIGRATION_GUIDE.md
git add migrations/docs/MIGRATION_QUICK_REFERENCE.md
git commit -m "Add PostgreSQL migration scripts and documentation"
git push origin main
```
