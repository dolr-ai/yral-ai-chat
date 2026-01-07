# Emergency Database Restore Guide

This guide covers emergency procedures for restoring the database from Litestream backups.

## Overview

The application uses Litestream for continuous SQLite replication to S3-compatible storage. In case of database corruption, deletion, or other emergencies, the database can be restored from backups.

## Automatic Restore

The application automatically attempts to restore the database on startup if:

1. **Database is missing**: The database file doesn't exist at the configured path
2. **Database is corrupted**: The database file exists but fails integrity checks

### Automatic Restore Process

1. **Detection**: On container startup, the entrypoint script checks if the database exists and is valid
2. **Backup**: If corrupted, the existing database is backed up with a timestamp
3. **Restore**: Litestream attempts to restore from the latest S3 backup
4. **Verification**: The restored database is verified for integrity
5. **Migrations**: Database migrations run to ensure schema compatibility
6. **Startup**: Application starts normally

### Logs

Monitor container logs to see restore activity:

```bash
docker-compose logs yral-ai-chat | grep -i restore
```

Look for messages like:
- `DATABASE RESTORE REQUIRED`
- `Database successfully restored and verified`
- `WARNING: No backup found or restore failed`

## Manual Restore Procedures

### Prerequisites

1. **Access to container**: SSH or Docker exec access
2. **Environment variables**: Litestream credentials must be set
3. **Backup exists**: Verify backup exists before attempting restore

### Verify Backup Exists

Before attempting a restore, verify that backups exist:

```bash
# Inside container
python3 /app/scripts/verify_backup.py
```

Or check directly with Litestream:

```bash
# Generate config (if needed)
export DATABASE_PATH=/app/data/yral_chat.db
# ... set other LITESTREAM_* env vars ...

# Check snapshots
litestream snapshots -config /tmp/litestream.yml $DATABASE_PATH
```

### Option 1: Emergency Restore Script

Use the provided emergency restore script:

```bash
# Inside container or on host
./scripts/emergency_restore.sh
```

**Options:**
- `--timestamp TIMESTAMP`: Restore to specific point in time (ISO format)
- `--force`: Force restore even if database exists
- `--no-backup`: Skip backing up existing database

**Example:**
```bash
# Restore to specific time
./scripts/emergency_restore.sh --timestamp "2024-01-15T10:30:00Z"

# Force restore (overwrites existing)
./scripts/emergency_restore.sh --force
```

### Option 2: Manual Litestream Restore

If the script is not available, restore manually:

```bash
# 1. Generate Litestream config
cat > /tmp/litestream.yml <<EOF
dbs:
  - path: /app/data/yral_chat.db
    replicas:
      - type: s3
        bucket: ${LITESTREAM_BUCKET}
        path: yral-ai-chat/yral_chat.db
        endpoint: ${LITESTREAM_ENDPOINT}
        region: ${LITESTREAM_REGION}
        access-key-id: ${LITESTREAM_ACCESS_KEY_ID}
        secret-access-key: ${LITESTREAM_SECRET_ACCESS_KEY}
EOF

# 2. Backup existing database (if exists)
cp /app/data/yral_chat.db /app/data/yral_chat.db.backup.$(date +%s)

# 3. Restore from backup
litestream restore -if-db-not-exists -if-replica-exists \
  -config /tmp/litestream.yml \
  /app/data/yral_chat.db

# 4. Verify restored database
python3 /app/scripts/verify_database.py

# 5. Run migrations (if needed)
python3 /app/scripts/run_migrations.py
```

### Option 3: Point-in-Time Restore

Restore to a specific point in time:

```bash
# Restore to specific timestamp
litestream restore \
  -config /tmp/litestream.yml \
  -timestamp "2024-01-15T10:30:00Z" \
  /app/data/yral_chat.db
```

**Note**: Point-in-time restore requires WAL files to be available in S3. Retention period is 24 hours by default.

## Recovery Scenarios

### Scenario 1: Database Deleted

**Symptoms:**
- Application fails to start
- Database file missing
- Logs show "Database not found"

**Solution:**
1. Restart container (automatic restore will trigger)
2. Or run manual restore script
3. Verify application starts successfully

### Scenario 2: Database Corrupted

**Symptoms:**
- Application fails to start
- Database file exists but verification fails
- SQLite errors in logs

**Solution:**
1. Corrupted database is automatically backed up on startup
2. Automatic restore will attempt to restore from backup
3. If automatic restore fails, use manual restore script
4. Check backup location: `/app/data/yral_chat.db.corrupted.*`

### Scenario 3: Backup Too Old

**Symptoms:**
- Restore succeeds but data is outdated
- Backup age exceeds retention period (24h default)

**Solution:**
1. Check backup age: `python3 /app/scripts/verify_backup.py`
2. If backup is too old, consider:
   - Restoring to latest available point
   - Accepting data loss for period beyond retention
   - Implementing longer retention if needed

### Scenario 4: S3 Connectivity Issues

**Symptoms:**
- Restore fails with S3 errors
- "No backup found" messages
- Litestream connectivity check fails

**Solution:**
1. Verify S3 credentials: `echo $LITESTREAM_ACCESS_KEY_ID`
2. Test S3 connectivity: `litestream databases -config /tmp/litestream.yml`
3. Check network connectivity to S3 endpoint
4. Verify bucket exists and is accessible
5. Check IAM permissions for S3 access

### Scenario 5: Restore Fails After Success

**Symptoms:**
- Restore command succeeds
- Database verification fails
- Application won't start

**Solution:**
1. Check restore logs for errors
2. Verify backup integrity in S3
3. Try restoring to earlier point in time
4. Check disk space and permissions
5. Review application logs for specific errors

## Verification Steps

After restore, always verify:

1. **Database exists and has content:**
   ```bash
   ls -lh /app/data/yral_chat.db
   python3 /app/scripts/verify_database.py
   ```

2. **Database integrity:**
   ```bash
   sqlite3 /app/data/yral_chat.db "PRAGMA integrity_check;"
   ```

3. **Expected tables exist:**
   ```bash
   sqlite3 /app/data/yral_chat.db ".tables"
   ```

4. **Application can connect:**
   ```bash
   # Check health endpoint
   curl http://localhost:8000/health
   ```

5. **Data is present:**
   ```bash
   sqlite3 /app/data/yral_chat.db "SELECT COUNT(*) FROM conversations;"
   ```

## Prevention

To prevent the need for emergency restores:

1. **Regular Backup Verification:**
   ```bash
   # Run before deployments
   python3 /app/scripts/verify_backup.py
   ```

2. **Monitor Litestream Status:**
   ```bash
   # Check replication status
   litestream databases -config /tmp/litestream.yml
   ```

3. **Test Restore Procedures:**
   - Test restore in staging environment
   - Document any environment-specific steps
   - Keep restore procedures up to date

4. **Monitor Application Logs:**
   - Watch for restore events
   - Alert on restore failures
   - Track backup age

## Troubleshooting

### Restore Command Not Found

If `litestream` command is not available:

```bash
# Check if Litestream is installed
which litestream

# If not installed, install it
# See Dockerfile for installation steps
```

### Permission Denied

If restore fails due to permissions:

```bash
# Check file permissions
ls -la /app/data/

# Fix permissions if needed
chmod 644 /app/data/yral_chat.db
chown $(whoami) /app/data/yral_chat.db
```

### Backup Path Mismatch

If restore can't find backup:

1. Verify S3 path matches database filename
2. Check `LITESTREAM_BUCKET` environment variable
3. Verify path in Litestream config matches S3 structure

### Migration Failures After Restore

If migrations fail after restore:

1. Check migration logs
2. Verify restored database schema version
3. May need to restore to point before problematic migration
4. Consider running migrations manually

## Support

For additional help:

1. Check application logs: `docker-compose logs yral-ai-chat`
2. Review Litestream documentation: https://litestream.io/
3. Check backup verification script output
4. Review container startup logs for restore events

## Related Documentation

- [Database Architecture](../architecture/database.md)
- [Development Guide](../development/development-guide.md)
- [Testing Guide](../development/testing-guide.md)

