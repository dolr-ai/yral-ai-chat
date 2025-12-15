#!/bin/bash
# Setup script for SQLite + Litestream on production server
# Run this on your production server

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo "=========================================="
echo "🔧 Yral AI Chat - SQLite + Litestream Setup"
echo "=========================================="
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo -e "${RED}Error: Please run as root${NC}"
    exit 1
fi

cd /root/yral-ai-chat

# Step 1: Install Litestream
echo ""
echo "📦 Step 1: Installing Litestream..."
echo "------------------------------------"

if command -v litestream &> /dev/null; then
    echo -e "${GREEN}✓ Litestream is already installed${NC}"
    litestream version
else
    echo "Downloading Litestream..."
    wget -q https://github.com/benbjohnson/litestream/releases/download/v0.3.13/litestream-v0.3.13-linux-amd64.deb
    dpkg -i litestream-v0.3.13-linux-amd64.deb
    rm litestream-v0.3.13-linux-amd64.deb
    echo -e "${GREEN}✓ Litestream installed${NC}"
    litestream version
fi

# Step 2: Install Python dependencies
echo ""
echo "📦 Step 2: Installing Python dependencies..."
echo "---------------------------------------------"

source venv/bin/activate
pip install --quiet aiosqlite
echo -e "${GREEN}✓ aiosqlite installed${NC}"

# Step 3: Create data directory
echo ""
echo "📁 Step 3: Creating data directory..."
echo "--------------------------------------"

mkdir -p /root/yral-ai-chat/data
mkdir -p /root/yral-ai-chat/logs
echo -e "${GREEN}✓ Directories created${NC}"

# Step 4: Create SQLite database and run migration
echo ""
echo "🗄️ Step 4: Creating SQLite database..."
echo "---------------------------------------"

# Create fresh database with schema
echo "Creating fresh database with schema..."
python scripts/run_migrations.py

# Enable WAL mode
sqlite3 /root/yral-ai-chat/data/yral_chat.db "PRAGMA journal_mode=WAL;"
echo -e "${GREEN}✓ SQLite database ready with WAL mode${NC}"

# Step 5: Setup Litestream service
echo ""
echo "🔄 Step 5: Setting up Litestream service..."
echo "--------------------------------------------"

# Copy service file
cp /root/yral-ai-chat/config/litestream.service /etc/systemd/system/litestream.service

# Reload systemd
systemctl daemon-reload

# Enable and start Litestream
systemctl enable litestream
systemctl start litestream

sleep 2

if systemctl is-active --quiet litestream; then
    echo -e "${GREEN}✓ Litestream service is running${NC}"
else
    echo -e "${YELLOW}⚠ Litestream service may have issues. Check logs:${NC}"
    echo "  journalctl -u litestream -f"
fi

# Step 6: Update application service
echo ""
echo "🚀 Step 6: Setting up application service..."
echo "---------------------------------------------"

# Copy updated service file
cp /root/yral-ai-chat/yral-ai-chat.service /etc/systemd/system/yral-ai-chat.service

# Reload systemd
systemctl daemon-reload

# Enable service
systemctl enable yral-ai-chat

echo -e "${GREEN}✓ Application service configured${NC}"

# Step 7: Check .env file
echo ""
echo "📝 Step 7: Checking configuration..."
echo "-------------------------------------"

if [ -f "/root/yral-ai-chat/.env" ]; then
    # Check if DATABASE_PATH is set
    if grep -q "DATABASE_PATH" /root/yral-ai-chat/.env; then
        echo -e "${GREEN}✓ .env file has DATABASE_PATH configured${NC}"
    else
        echo -e "${YELLOW}⚠ Adding DATABASE_PATH to .env...${NC}"
        echo "" >> /root/yral-ai-chat/.env
        echo "# SQLite Database" >> /root/yral-ai-chat/.env
        echo "DATABASE_PATH=/root/yral-ai-chat/data/yral_chat.db" >> /root/yral-ai-chat/.env
        echo -e "${GREEN}✓ DATABASE_PATH added to .env${NC}"
    fi
else
    echo -e "${YELLOW}⚠ No .env file found. Please create one from env.example${NC}"
    echo "  cp env.example .env"
    echo "  nano .env"
fi

# Summary
echo ""
echo "=========================================="
echo -e "${GREEN}✅ Setup Complete!${NC}"
echo "=========================================="
echo ""
echo "What was configured:"
echo "  ✓ Litestream installed and running"
echo "  ✓ SQLite database created with data"
echo "  ✓ WAL mode enabled for Litestream"
echo "  ✓ Systemd services configured"
echo ""
echo "Next steps:"
echo "  1. Verify .env configuration:"
echo "     nano /root/yral-ai-chat/.env"
echo ""
echo "  2. Start the application:"
echo "     systemctl start yral-ai-chat"
echo ""
echo "  3. Check status:"
echo "     systemctl status yral-ai-chat"
echo "     systemctl status litestream"
echo ""
echo "  4. Test the API:"
echo "     curl http://localhost:8000/health"
echo ""
echo "  5. Check Litestream replication:"
echo "     tail -f /root/yral-ai-chat/logs/litestream.log"
echo ""
echo "Service commands:"
echo "  Start app:    systemctl start yral-ai-chat"
echo "  Stop app:     systemctl stop yral-ai-chat"
echo "  Restart app:  systemctl restart yral-ai-chat"
echo "  App logs:     journalctl -u yral-ai-chat -f"
echo "  Litestream:   journalctl -u litestream -f"
echo ""

