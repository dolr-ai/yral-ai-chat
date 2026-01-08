# Emergency Database Restore Guide

This guide covers automatic database restore procedures from Litestream backups.

## Overview

The application uses Litestream for continuous SQLite replication to S3-compatible storage. The database is automatically restored on container startup if it's missing or corrupted.

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

### Checking Restore Status

Since you may not have direct access to Docker logs, you can check restore status via the API:

**Via Health Endpoint:**
```bash
curl http://your-domain.com/health | jq '.services.database_restore'
```

If a restore happened recently, you'll see:
```json
{
  "status": "up",
  "error": "Database restored recently (database_modified_after_startup)"
}
```

**Via GitHub Actions Logs:**
Check deployment logs for restore messages:
- `DATABASE RESTORE REQUIRED`
- `✓ Database successfully restored and verified`
- `⚠ WARNING: Database restore failed`

**Manual Verification:**
```bash
# Check if database was recently created/modified
docker-compose exec yral-ai-chat ls -lh /app/data/yral_chat.db

# Verify database integrity
docker-compose exec yral-ai-chat python3 /app/scripts/verify_database.py
```

## Recovery Scenarios

### Scenario 1: Database Deleted

**Symptoms:**
- Application fails to start
- Database file missing
- Logs show "Database not found"

**Solution:**
1. Restart container (automatic restore will trigger)
2. Monitor logs for restore messages
3. Verify application starts successfully

### Scenario 2: Database Corrupted

**Symptoms:**
- Application fails to start
- Database file exists but verification fails
- SQLite errors in logs

**Solution:**
1. Corrupted database is automatically backed up on startup
2. Automatic restore will attempt to restore from backup
3. Check backup location: `/app/data/yral_chat.db.corrupted.*`
4. If automatic restore fails, check logs for specific errors

### Scenario 3: Backup Too Old

**Symptoms:**
- Restore succeeds but data is outdated
- Backup age exceeds retention period (24h default)

**Solution:**
1. Check backup age using Litestream commands:
   ```bash
   docker-compose exec yral-ai-chat litestream snapshots -config /tmp/litestream.yml /app/data/yral_chat.db
   ```
2. If backup is too old, consider:
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

1. **Monitor Litestream Status:**
   ```bash
   # Check replication status
   docker-compose exec yral-ai-chat litestream databases -config /tmp/litestream.yml
   ```

2. **Monitor Application Logs:**
   - Watch for restore events
   - Alert on restore failures
   - Track backup age

3. **Regular Health Checks:**
   - Monitor `/health` endpoint for Litestream status
   - Set up alerts for restore events
   - Track database integrity over time

## Troubleshooting

### Automatic Restore Not Triggering

If automatic restore doesn't trigger:

1. Check container logs for restore messages
2. Verify Litestream environment variables are set
3. Ensure database path is correct
4. Check if database file exists (restore only triggers if missing or corrupted)

### Restore Fails

If automatic restore fails:

1. Check container logs for specific error messages
2. Verify S3 connectivity and credentials
3. Check if backup exists in S3
4. Verify disk space and permissions
5. Review Litestream configuration

### Permission Denied

If restore fails due to permissions:

```bash
# Check file permissions
docker-compose exec yral-ai-chat ls -la /app/data/

# Fix permissions if needed (inside container)
docker-compose exec yral-ai-chat chmod 644 /app/data/yral_chat.db
```

### Backup Path Mismatch

If restore can't find backup:

1. Verify S3 path matches database filename
2. Check `LITESTREAM_BUCKET` environment variable
3. Verify path in Litestream config matches S3 structure
4. Check container logs for path-related errors

### Migration Failures After Restore

If migrations fail after restore:

1. Check migration logs in container output
2. Verify restored database schema version
3. Review application startup logs
4. Check if migrations need to be run manually

## Support

For additional help:

1. Check application logs: `docker-compose logs yral-ai-chat`
2. Review Litestream documentation: https://litestream.io/
3. Review container startup logs for restore events
4. Check health endpoint: `curl http://localhost:8000/health`

## Related Documentation

- [Database Architecture](../architecture/database.md)
- [Development Guide](../development/development-guide.md)
- [Testing Guide](../development/testing-guide.md)
