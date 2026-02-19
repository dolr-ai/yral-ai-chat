#!/bin/sh
set -e

echo "Starting yral-ai-chat..."

# Restore database from Litestream if enabled and database doesn't exist
if [ "${ENABLE_LITESTREAM}" = "true" ] && [ ! -f /app/data/yral_chat.db ]; then
    echo "No local database found. Attempting Litestream restore..."
    litestream restore -if-replica-exists -config /etc/litestream.yml /app/data/yral_chat.db || {
        echo "No replica found or restore failed. Starting fresh."
    }
fi

# Start Litestream replication in background if enabled
if [ "${ENABLE_LITESTREAM}" = "true" ]; then
    echo "Starting Litestream replication..."
    exec litestream replicate -config /etc/litestream.yml -exec "/app/yral-ai-chat"
else
    echo "Litestream disabled. Starting server directly..."
    exec /app/yral-ai-chat
fi
