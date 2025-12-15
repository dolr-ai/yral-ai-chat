#!/bin/bash
set -e

echo "=========================================="
echo "🚀 Litestream Production Installation"
echo "=========================================="
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo -e "${RED}❌ Please run as root (use sudo)${NC}"
    exit 1
fi

echo "Step 1: Downloading Litestream..."
cd /tmp
wget -q https://github.com/benbjohnson/litestream/releases/download/v0.3.13/litestream-v0.3.13-linux-amd64.tar.gz
tar -xzf litestream-v0.3.13-linux-amd64.tar.gz
mv litestream /usr/local/bin/
chmod +x /usr/local/bin/litestream
rm litestream-v0.3.13-linux-amd64.tar.gz
echo -e "${GREEN}✓ Litestream binary installed${NC}"

echo ""
echo "Step 2: Verifying installation..."
/usr/local/bin/litestream version
echo -e "${GREEN}✓ Version verified${NC}"

echo ""
echo "Step 3: Checking database WAL mode..."
DB_PATH="/root/yral-ai-chat/data/yral_chat.db"
if [ ! -f "$DB_PATH" ]; then
    echo -e "${RED}❌ Database not found at: $DB_PATH${NC}"
    echo "Please ensure your application is deployed first."
    exit 1
fi

WAL_MODE=$(sqlite3 "$DB_PATH" "PRAGMA journal_mode;")
if [ "$WAL_MODE" != "wal" ]; then
    echo -e "${YELLOW}⚠ Database not in WAL mode. Enabling...${NC}"
    sqlite3 "$DB_PATH" "PRAGMA journal_mode=WAL;"
    echo -e "${GREEN}✓ WAL mode enabled${NC}"
else
    echo -e "${GREEN}✓ Database already in WAL mode${NC}"
fi

echo ""
echo "Step 4: Installing systemd service..."
cp /root/yral-ai-chat/config/litestream.service /etc/systemd/system/
systemctl daemon-reload
echo -e "${GREEN}✓ Service file installed${NC}"

echo ""
echo "Step 5: Verifying configuration..."
if [ ! -f "/root/yral-ai-chat/config/litestream.yml" ]; then
    echo -e "${RED}❌ Configuration file not found${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Configuration file found${NC}"

echo ""
echo "Step 6: Starting Litestream service..."
systemctl enable litestream
systemctl start litestream
echo -e "${GREEN}✓ Service started and enabled${NC}"

echo ""
echo "Step 7: Checking service status..."
sleep 2
systemctl status litestream --no-pager -l || true

echo ""
echo "=========================================="
echo -e "${GREEN}✅ Installation Complete!${NC}"
echo "=========================================="
echo ""
echo "Useful commands:"
echo "  • Check status:  systemctl status litestream"
echo "  • View logs:     journalctl -u litestream -f"
echo "  • Restart:       systemctl restart litestream"
echo "  • Stop:          systemctl stop litestream"
echo ""
echo "Your database is now being backed up to S3."
echo "Check your litestream.yml configuration for bucket details."
echo ""
echo "⚠️  Note: Keep the generation tracking errors in mind."
echo "    Snapshots are working, but generation metadata may"
echo "    have issues with Hetzner S3-compatible storage."
echo "=========================================="
