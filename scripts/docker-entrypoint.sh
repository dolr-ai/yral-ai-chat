#!/bin/bash
set -e

# ========================================================================================
# Yral AI Chat - Docker Entrypoint
# Handles database replication (Litestream), integrity checks, migrations, and process startup.
# ========================================================================================

echo "Starting Yral AI Chat API..."

# --- Configuration & Defaults ---
ENABLE_LITESTREAM=${ENABLE_LITESTREAM:-true}
DATABASE_PATH=${DATABASE_PATH:-/app/data/yral_chat.db}
DB_DIR=$(dirname "$DATABASE_PATH")
mkdir -p "$DB_DIR"

DB_FILENAME=$(basename "$DATABASE_PATH")
S3_PATH="yral-ai-chat/$DB_FILENAME"
LITESTREAM_CONFIG="/tmp/litestream.yml"

# Helper: Verify database integrity
verify_db() {
    local db="$1"
    echo "Verifying database at: $db"
    [ ! -f "$db" ] && { echo "Database does not exist."; return 1; }
    [ ! -s "$db" ] && { echo "Database is empty."; return 1; }
    if python3 /app/scripts/verify_database.py 2>&1; then
        echo "✓ Database verification passed"
        return 0
    else
        echo "✗ Database verification failed"
        return 1
    fi
}

USE_LITESTREAM=false
if [ "$ENABLE_LITESTREAM" = "true" ] && [ -n "$LITESTREAM_BUCKET" ]; then
    USE_LITESTREAM=true
fi

# ========================================================================================
# Step 1: Litestream Configuration
# ========================================================================================
if [ "$USE_LITESTREAM" = "true" ]; then
    echo ">> Step 1: Configuring Litestream"
    
    # Export variables for envsubst
    export LITESTREAM_BUCKET LITESTREAM_ACCESS_KEY_ID LITESTREAM_SECRET_ACCESS_KEY \
           LITESTREAM_REGION LITESTREAM_ENDPOINT S3_PATH DATABASE_PATH

    # Generate config from template
    # Explicitly list variables to substitute for stricter security
    VARS='$LITESTREAM_BUCKET:$LITESTREAM_ACCESS_KEY_ID:$LITESTREAM_SECRET_ACCESS_KEY:$LITESTREAM_REGION:$LITESTREAM_ENDPOINT:$S3_PATH:$DATABASE_PATH'
    
    if [ -f "/etc/litestream.yml" ]; then
        envsubst "$VARS" < /etc/litestream.yml > "$LITESTREAM_CONFIG"
        echo "✓ Generated Litestream config from template"
    else
        echo "✗ ERROR: Config template /etc/litestream.yml not found"
        exit 1
    fi
    
    # Verify S3 connectivity
    if litestream databases -config "$LITESTREAM_CONFIG" &>/dev/null; then
        echo "✓ Litestream S3 connectivity confirmed"
    else
        echo "⚠ WARNING: Litestream cannot connect to S3. Restore may fail."
    fi
fi

# ========================================================================================
# Step 2: Database Integrity & Restore Logic
# ========================================================================================
if [ "$USE_LITESTREAM" = "true" ]; then
    echo ">> Step 2: Checking Database Integrity"
    
    NEEDS_RESTORE=false
    
    if [ ! -f "$DATABASE_PATH" ]; then
        echo "⚠ Database missing. Marking for restore."
        NEEDS_RESTORE=true
    elif ! verify_db "$DATABASE_PATH"; then
        echo "⚠ Database corrupted. Backing up and marking for restore."
        mv "$DATABASE_PATH" "${DATABASE_PATH}.corrupted.$(date +%s)"
        NEEDS_RESTORE=true
    else
        echo "✓ Database exists and is valid. No restore needed."
    fi

    if [ "$NEEDS_RESTORE" = "true" ]; then
        echo ">> Step 2b: Restoring Database from S3"
        echo "   Source: s3://${LITESTREAM_BUCKET}/$S3_PATH"
        
        if litestream restore -if-db-not-exists -if-replica-exists -config "$LITESTREAM_CONFIG" "$DATABASE_PATH"; then
            echo "✓ Restore command completed."
            if verify_db "$DATABASE_PATH"; then
                echo "✓ Restored database verified successfully."
            else
                echo "✗ ERROR: Restored database failed verification! Manual intervention required."
                exit 1
            fi
        else
            echo "⚠ Restore failed or no backup found (normal for new deployments)."
        fi
    fi
fi

# ========================================================================================
# Step 3: Migrations
# ========================================================================================
echo ">> Step 3: Running Database Migrations"
if python3 /app/scripts/run_migrations.py; then
    echo "✓ Migrations completed successfully"
else
    echo "✗ ERROR: Migrations failed"
    exit 1
fi

# Final verification before startup
if ! verify_db "$DATABASE_PATH"; then
    echo "✗ ERROR: Final database integrity check failed. Aborting startup."
    exit 1
fi

# ========================================================================================
# Step 4: Process Startup
# ========================================================================================
echo ">> Step 4: Starting Services"

# Cleanup handler
cleanup() {
    echo "Stopping services..."
    [ -n "$APP_PID" ] && kill -TERM "$APP_PID" 2>/dev/null
    [ -n "$LITESTREAM_PID" ] && kill -TERM "$LITESTREAM_PID" 2>/dev/null
    wait
    exit 0
}
trap cleanup SIGTERM SIGINT

# Start Litestream (Background)
if [ "$USE_LITESTREAM" = "true" ]; then
    echo "   Starting Litestream replication..."
    litestream replicate -config "$LITESTREAM_CONFIG" &
    LITESTREAM_PID=$!
    
    sleep 1
    if ! kill -0 "$LITESTREAM_PID" 2>/dev/null; then
        echo "✗ ERROR: Litestream died on startup. Check logs."
        exit 1
    fi
    echo "✓ Litestream running (PID: $LITESTREAM_PID)"
else
    echo "   Litestream disabled. Running without replication."
fi

# Start Application (Background)
echo "   Starting Application: $@"
"$@" &
APP_PID=$!

sleep 2
if ! kill -0 "$APP_PID" 2>/dev/null; then
    echo "✗ ERROR: Application died on startup."
    exit 1
fi
echo "✓ Application running (PID: $APP_PID)"

# Monitor loop: Exit if EITHER process dies
# This ensures we don't run without backup (if Litestream dies) 
# or run a zombie container (if App dies)
echo "   Services started. Monitoring processes..."
while true; do
    if [ "$USE_LITESTREAM" = "true" ] && ! kill -0 "$LITESTREAM_PID" 2>/dev/null; then
        echo "✗ CRITICAL: Litestream process died! Shutting down container due to backup failure."
        kill -TERM "$APP_PID" 2>/dev/null
        exit 1
    fi
    
    if ! kill -0 "$APP_PID" 2>/dev/null; then
        echo "✗ CRITICAL: Application process died! Shutting down."
        [ -n "$LITESTREAM_PID" ] && kill -TERM "$LITESTREAM_PID" 2>/dev/null
        exit 1
    fi
    
    # Wait for any signal
    sleep 5 &
    wait $!
done
