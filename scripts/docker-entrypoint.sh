#!/bin/bash
set -e

echo "Starting Yral AI Chat API with Litestream..."

# Check if Litestream is enabled via environment variable
ENABLE_LITESTREAM=${ENABLE_LITESTREAM:-true}

if [ "$ENABLE_LITESTREAM" = "true" ]; then
    echo "Litestream is enabled"
    
    # Get database path from environment variable, default to production path
    DATABASE_PATH=${DATABASE_PATH:-/app/data/yral_chat.db}
    
    # Determine S3 path based on database filename
    DB_FILENAME=$(basename "$DATABASE_PATH")
    S3_PATH="yral-ai-chat/$DB_FILENAME"
    
    # Generate dynamic litestream config based on DATABASE_PATH
    # Only enable Litestream if required environment variables are set
    if [ -z "$LITESTREAM_BUCKET" ] || [ -z "$LITESTREAM_ACCESS_KEY_ID" ] || [ -z "$LITESTREAM_SECRET_ACCESS_KEY" ]; then
        echo "WARNING: Litestream environment variables not set, disabling Litestream replication"
        ENABLE_LITESTREAM=false
    else
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
        sync-interval: 10s
        retention: 24h
        retention-check-interval: 1h
        snapshot-interval: 1h
EOF
        echo "Generated Litestream config for database: $DATABASE_PATH"
        
        # Check if database exists, if not try to restore from backup
        if [ ! -f "$DATABASE_PATH" ]; then
            echo "Database not found at $DATABASE_PATH, attempting to restore from Litestream backup..."
            if litestream restore -if-db-not-exists -if-replica-exists -config "$LITESTREAM_CONFIG" "$DATABASE_PATH"; then
                echo "Database restored from backup"
            else
                echo "No backup found or restore failed, will create new database"
            fi
        else
            echo "Database file exists at $DATABASE_PATH"
        fi
        
        # Start Litestream replication in the background
        echo "Starting Litestream replication..."
        litestream replicate -config "$LITESTREAM_CONFIG" &
        LITESTREAM_PID=$!
        echo "Litestream started with PID: $LITESTREAM_PID"
    fi
    
    # Function to handle shutdown gracefully
    shutdown() {
        echo ""
        echo "Received shutdown signal, stopping services..."
        
        # Stop the application first
        if [ -n "$APP_PID" ]; then
            echo "   Stopping application (PID: $APP_PID)..."
            kill -TERM "$APP_PID" 2>/dev/null || true
            wait "$APP_PID" 2>/dev/null || true
        fi
        
        # Stop Litestream
        if [ -n "$LITESTREAM_PID" ]; then
            echo "   Stopping Litestream (PID: $LITESTREAM_PID)..."
            kill -TERM "$LITESTREAM_PID" 2>/dev/null || true
            wait "$LITESTREAM_PID" 2>/dev/null || true
        fi
        
        echo "Services stopped gracefully"
        exit 0
    }
    
    # Trap signals for graceful shutdown
    trap shutdown SIGTERM SIGINT
    
    # Start the application
    echo "Starting application..."
    "$@" &
    APP_PID=$!
    echo "Application started with PID: $APP_PID"
    
    # Wait a moment and check if the process is still running
    sleep 2
    if ! kill -0 "$APP_PID" 2>/dev/null; then
        echo "ERROR: Application process died immediately after startup"
        exit 1
    fi
    
    # Wait for the application process
    wait "$APP_PID"
    EXIT_CODE=$?
    echo "Application exited with code: $EXIT_CODE"
    exit $EXIT_CODE
    
else
    echo "Litestream is disabled (ENABLE_LITESTREAM=false)"
    echo "Starting application without Litestream..."
    exec "$@"
fi
