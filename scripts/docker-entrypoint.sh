#!/bin/bash
set -e

echo "🚀 Starting Yral AI Chat API with Litestream..."

# Check if Litestream is enabled via environment variable
ENABLE_LITESTREAM=${ENABLE_LITESTREAM:-true}

if [ "$ENABLE_LITESTREAM" = "true" ]; then
    echo "📦 Litestream is enabled"
    
    # Check if database exists, if not try to restore from backup
    if [ ! -f "/app/data/yral_chat.db" ]; then
        echo "🗄️  Database not found, attempting to restore from Litestream backup..."
        if litestream restore -if-db-not-exists -if-replica-exists -config /etc/litestream.yml /app/data/yral_chat.db; then
            echo "✅ Database restored from backup"
        else
            echo "ℹ️  No backup found or restore failed, will create new database"
        fi
    else
        echo "✅ Database file exists"
    fi
    
    # Start Litestream replication in the background
    echo "🔄 Starting Litestream replication..."
    litestream replicate -config /etc/litestream.yml &
    LITESTREAM_PID=$!
    echo "✅ Litestream started with PID: $LITESTREAM_PID"
    
    # Function to handle shutdown gracefully
    shutdown() {
        echo ""
        echo "🛑 Received shutdown signal, stopping services..."
        
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
        
        echo "✅ Services stopped gracefully"
        exit 0
    }
    
    # Trap signals for graceful shutdown
    trap shutdown SIGTERM SIGINT
    
    # Start the application
    echo "🚀 Starting application..."
    "$@" &
    APP_PID=$!
    echo "✅ Application started with PID: $APP_PID"
    
    # Wait for the application process
    wait "$APP_PID"
    
else
    echo "⚠️  Litestream is disabled (ENABLE_LITESTREAM=false)"
    echo "🚀 Starting application without Litestream..."
    exec "$@"
fi
