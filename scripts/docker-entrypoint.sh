#!/bin/bash
set -e

echo "Starting Yral AI Chat API with Litestream..."

ENABLE_LITESTREAM=${ENABLE_LITESTREAM:-true}
DATABASE_PATH=${DATABASE_PATH:-/app/data/yral_chat.db}
mkdir -p "$(dirname "$DATABASE_PATH")"

verify_database() {
    local db_path="$1"
    echo "Verifying database integrity at: $db_path"
    
    if [ ! -f "$db_path" ]; then
        echo "Database file does not exist"
        return 1
    fi
    
    if [ ! -s "$db_path" ]; then
        echo "Database file is empty"
        return 1
    fi
    
    if python3 /app/scripts/verify_database.py 2>&1; then
        echo "Database verification passed"
        return 0
    else
        echo "Database verification failed"
        return 1
    fi
}

USE_LITESTREAM=false
if [ "$ENABLE_LITESTREAM" = "true" ]; then
    if [ -n "$LITESTREAM_BUCKET" ] && [ -n "$LITESTREAM_ACCESS_KEY_ID" ] && [ -n "$LITESTREAM_SECRET_ACCESS_KEY" ]; then
        USE_LITESTREAM=true
        echo "Litestream is enabled"
    else
        echo "WARNING: Litestream environment variables not set, disabling Litestream replication"
    fi
fi

if [ "$USE_LITESTREAM" = "true" ]; then
    DB_FILENAME=$(basename "$DATABASE_PATH")
    S3_PATH="yral-ai-chat/$DB_FILENAME"
    LITESTREAM_CONFIG="/tmp/litestream.yml"
    cat > "$LITESTREAM_CONFIG" <<EOF
# Litestream Configuration (generated dynamically)
dbs:
  - path: $DATABASE_PATH
    replicas:
      - type: s3
        bucket: ${LITESTREAM_BUCKET}
        path: $S3_PATH
        endpoint: ${LITESTREAM_ENDPOINT}
        region: ${LITESTREAM_REGION}
        access-key-id: ${LITESTREAM_ACCESS_KEY_ID}
        secret-access-key: ${LITESTREAM_SECRET_ACCESS_KEY}
        sync-interval: 1s
        retention: 720h
        retention-check-interval: 1h
        snapshot-interval: 1h
EOF
    echo "Generated Litestream config for database: $DATABASE_PATH"
    echo "S3 backup path: s3://${LITESTREAM_BUCKET}/$S3_PATH"
    
    check_litestream_connectivity() {
        echo "Checking Litestream connectivity to S3..."
        if litestream databases -config "$LITESTREAM_CONFIG" &>/dev/null; then
            echo "✓ Litestream can connect to S3"
            return 0
        else
            echo "⚠ WARNING: Litestream connectivity check failed"
            echo "  This may indicate S3 connectivity issues"
            echo "  Restore may fail if backup is needed"
            return 1
        fi
    }
    
    check_litestream_connectivity || true
    echo ""
    
    # Step 1: Check if database exists and is valid
    NEEDS_RESTORE=false
    RESTORE_REASON=""
    RESTORE_STATUS="not_needed"
    
    if [ ! -f "$DATABASE_PATH" ]; then
        echo "⚠ Database not found at $DATABASE_PATH"
        RESTORE_REASON="database file missing"
        NEEDS_RESTORE=true
    elif ! verify_database "$DATABASE_PATH"; then
        echo "⚠ Existing database file is corrupted or invalid"
        echo "  Backing up corrupted database before restore attempt..."
        CORRUPTED_BACKUP="${DATABASE_PATH}.corrupted.$(date +%s)"
        if mv "$DATABASE_PATH" "$CORRUPTED_BACKUP" 2>/dev/null; then
            echo "  Corrupted database backed up to: $CORRUPTED_BACKUP"
            RESTORE_REASON="database corruption detected"
        else
            echo "  WARNING: Could not backup corrupted database"
            rm -f "$DATABASE_PATH" 2>/dev/null || true
            RESTORE_REASON="database corruption detected (backup failed)"
        fi
        NEEDS_RESTORE=true
    else
        echo "✓ Database file exists and is valid at $DATABASE_PATH"
        RESTORE_STATUS="database_valid"
    fi
    
    # Step 2: Restore from backup if needed
    if [ "$NEEDS_RESTORE" = "true" ]; then
        echo ""
        echo "=========================================="
        echo "DATABASE RESTORE REQUIRED"
        echo "=========================================="
        echo "Reason: $RESTORE_REASON"
        echo "Attempting to restore database from Litestream backup..."
        echo "S3 path: s3://${LITESTREAM_BUCKET}/$S3_PATH"
        echo ""
        
        RESTORE_START_TIME=$(date +%s)
        if litestream restore -if-db-not-exists -if-replica-exists -config "$LITESTREAM_CONFIG" "$DATABASE_PATH" 2>&1; then
            RESTORE_END_TIME=$(date +%s)
            RESTORE_DURATION=$((RESTORE_END_TIME - RESTORE_START_TIME))
            echo ""
            echo "✓ Database restore command completed successfully (took ${RESTORE_DURATION}s)"
            
            # Step 3: Verify restored database
            echo "Verifying restored database..."
            if verify_database "$DATABASE_PATH"; then
                echo "✓ Database successfully restored and verified"
                echo "  Restore completed at $(date -Iseconds)"
                echo "=========================================="
                RESTORE_STATUS="success"
            else
                echo ""
                echo "✗ ERROR: Database restore completed but verification failed!"
                echo "  The restored database may be corrupted or incomplete."
                echo "  This could indicate:"
                echo "    - Backup corruption"
                echo "    - Incomplete restore"
                echo "    - Network issues during restore"
                echo ""
                echo "  Exiting to prevent data loss."
                echo "  Manual intervention required."
                echo "  See docs/operations/emergency-restore.md for recovery procedures"
                exit 1
            fi
        else
            RESTORE_EXIT_CODE=$?
            echo ""
            echo "⚠ WARNING: Database restore failed (exit code: $RESTORE_EXIT_CODE)"
            echo "  Possible reasons:"
            echo "    - No backup exists yet (normal for new deployments)"
            echo "    - S3 connectivity issues"
            echo "    - Invalid S3 credentials"
            echo "    - Backup path mismatch"
            echo ""
            echo "  A new database will be created when migrations run"
            echo "  If this is unexpected, check:"
            echo "    - S3 backup exists: litestream snapshots -config $LITESTREAM_CONFIG $DATABASE_PATH"
            echo "    - S3 connectivity: litestream databases -config $LITESTREAM_CONFIG"
            echo ""

            RESTORE_STATUS="failed_no_backup"
        fi
        echo ""
    fi
    
    # Log restore status summary for visibility in deployment logs
    echo ""
    echo "=========================================="
    echo "DATABASE RESTORE STATUS SUMMARY"
    echo "=========================================="
    case "$RESTORE_STATUS" in
        "success")
            echo "✓ RESTORE: Database was successfully restored from backup"
            ;;
        "failed_no_backup")
            echo "⚠ RESTORE: Restore attempted but no backup found (new deployment)"
            ;;
        "database_valid")
            echo "✓ RESTORE: No restore needed - database exists and is valid"
            ;;
        "not_needed")
            echo "✓ RESTORE: No restore needed - database exists and is valid"
            ;;
        *)
            echo "ℹ RESTORE: Status unknown"
            ;;
    esac
    echo "=========================================="
    echo ""
    
    # Step 4: Run migrations (creates database if missing, updates schema if needed)
    echo "Running database migrations..."
    if python3 /app/scripts/run_migrations.py; then
        echo "✓ Database migrations completed successfully"
    else
        echo "ERROR: Database migrations failed!"
        exit 1
    fi
    
    # Step 5: Final verification after migrations
    echo "Verifying database after migrations..."
    if verify_database "$DATABASE_PATH"; then
        echo "✓ Database verification passed after migrations"
    else
        echo "ERROR: Database verification failed after migrations!"
        exit 1
    fi
    
    echo "Starting Litestream replication..."
    echo "  Config: $LITESTREAM_CONFIG"
    echo "  Database: $DATABASE_PATH"
    echo "  S3 path: s3://${LITESTREAM_BUCKET}/$S3_PATH"
    echo "  Sync interval: 1s"
    echo "  Retention: 720h"
    litestream replicate -config "$LITESTREAM_CONFIG" &
    LITESTREAM_PID=$!
    echo "✓ Litestream started with PID: $LITESTREAM_PID"
    
    sleep 1
    if ! kill -0 "$LITESTREAM_PID" 2>/dev/null; then
        echo "✗ ERROR: Litestream process died immediately after startup"
        echo "  Check Litestream logs and S3 configuration"
        exit 1
    fi
    echo ""
    
    shutdown() {
        echo ""
        echo "Received shutdown signal, stopping services..."
        
        if [ -n "$APP_PID" ]; then
            echo "   Stopping application (PID: $APP_PID)..."
            kill -TERM "$APP_PID" 2>/dev/null || true
            wait "$APP_PID" 2>/dev/null || true
        fi
        
        if [ -n "$LITESTREAM_PID" ]; then
            echo "   Stopping Litestream (PID: $LITESTREAM_PID)..."
            kill -TERM "$LITESTREAM_PID" 2>/dev/null || true
            wait "$LITESTREAM_PID" 2>/dev/null || true
        fi
        
        echo "Services stopped gracefully"
        exit 0
    }
    
    trap shutdown SIGTERM SIGINT
    
    echo "Starting application..."
    echo "Command: $@"
    echo "Working directory: $(pwd)"
    echo "Environment: ENVIRONMENT=${ENVIRONMENT:-not set}, DATABASE_PATH=${DATABASE_PATH}"
    
    "$@" &
    APP_PID=$!
    echo "Application started with PID: $APP_PID"
    
    sleep 3
    if ! kill -0 "$APP_PID" 2>/dev/null; then
        echo "ERROR: Application process died immediately after startup"
        echo "Checking if process exists..."
        ps aux | grep -E "(uvicorn|python)" | grep -v grep || echo "No uvicorn/python processes found"
        echo "Checking for error logs..."
        exit 1
    fi
    
    echo "Application is running (PID: $APP_PID)"
    echo "Checking if port 8000 is listening..."
    sleep 2
    if command -v netstat >/dev/null 2>&1; then
        netstat -tlnp 2>/dev/null | grep 8000 || echo "WARNING: Port 8000 not found in netstat"
    fi
    
    wait "$APP_PID"
    EXIT_CODE=$?
    echo "Application exited with code: $EXIT_CODE"
    exit $EXIT_CODE
    
else
    echo "Litestream is disabled or not configured"
    echo "Starting application without Litestream..."
    
    if [ -f "$DATABASE_PATH" ]; then
        if ! verify_database "$DATABASE_PATH"; then
            echo "WARNING: Database verification failed, but continuing without Litestream restore"
        fi
    fi
    
    echo "Running database migrations..."
    python3 /app/scripts/run_migrations.py || {
        echo "ERROR: Database migrations failed!"
        exit 1
    }
    
    echo "Command: $@"
    echo "Working directory: $(pwd)"
    echo "Environment: ENVIRONMENT=${ENVIRONMENT:-not set}, DATABASE_PATH=${DATABASE_PATH}"
    exec "$@"
fi
