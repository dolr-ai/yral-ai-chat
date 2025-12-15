#!/bin/bash
# Start Litestream for local development (macOS)

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo "=========================================="
echo "🔄 Starting Litestream (Local Development)"
echo "=========================================="
echo ""

# Check if litestream is installed
LITESTREAM_BIN=""
if [ -f "./bin/litestream" ]; then
    LITESTREAM_BIN="./bin/litestream"
elif command -v litestream &> /dev/null; then
    LITESTREAM_BIN="litestream"
else
    echo -e "${RED}❌ Litestream is not installed${NC}"
    echo ""
    echo "It should be in ./bin/litestream"
    echo "If missing, download it:"
    echo "  curl -L https://github.com/benbjohnson/litestream/releases/download/v0.3.13/litestream-v0.3.13-darwin-amd64.zip -o /tmp/litestream.zip"
    echo "  unzip /tmp/litestream.zip -d bin/"
    echo "  chmod +x bin/litestream"
    echo ""
    exit 1
fi

echo -e "${GREEN}✓ Litestream found:${NC} $($LITESTREAM_BIN version)"
echo ""

# Check if database exists
if [ ! -f "data/yral_chat.db" ]; then
    echo -e "${RED}❌ Database not found: data/yral_chat.db${NC}"
    exit 1
fi

# Check WAL mode
JOURNAL_MODE=$(sqlite3 data/yral_chat.db "PRAGMA journal_mode;" 2>&1)
if [ "$JOURNAL_MODE" != "wal" ]; then
    echo -e "${YELLOW}⚠ Database is not in WAL mode, enabling...${NC}"
    sqlite3 data/yral_chat.db "PRAGMA journal_mode=WAL;"
    echo -e "${GREEN}✓ WAL mode enabled${NC}"
else
    echo -e "${GREEN}✓ Database is in WAL mode${NC}"
fi

echo ""
echo "Starting Litestream replication..."
echo "  Database: ./data/yral_chat.db"
echo "  S3 Bucket: postgres-1-backup"
echo "  S3 Path: yral-ai-chat-dev/db"
echo ""
echo "Press Ctrl+C to stop"
echo "=========================================="
echo ""

# Start Litestream
$LITESTREAM_BIN replicate -config config/litestream-local.yml
