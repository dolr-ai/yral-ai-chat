#!/bin/bash
# Setup systemd service for Yral AI Chat API

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo "🔧 Setting up Yral AI Chat as a systemd service"
echo "==============================================="
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo -e "${RED}Error: Please run as root (use sudo)${NC}"
    exit 1
fi

# Stop any running uvicorn processes
echo "Stopping any existing uvicorn processes..."
pkill -f "uvicorn src.main:app" || true
sleep 2

# Create logs directory
mkdir -p /root/yral-ai-chat/logs

# Copy service file
echo "Installing systemd service file..."
cp /root/yral-ai-chat/yral-ai-chat.service /etc/systemd/system/yral-ai-chat.service

# Reload systemd
echo "Reloading systemd daemon..."
systemctl daemon-reload

# Enable service to start on boot
echo "Enabling service..."
systemctl enable yral-ai-chat.service

# Start service
echo "Starting service..."
systemctl start yral-ai-chat.service

# Wait a moment for it to start
sleep 3

# Check status
echo ""
echo "=========================================="
echo -e "${GREEN}Service Status:${NC}"
echo "=========================================="
systemctl status yral-ai-chat.service --no-pager || true

echo ""
echo "=========================================="
echo -e "${GREEN}Setup Complete!${NC}"
echo "=========================================="
echo ""
echo "Service Management Commands:"
echo "  Start:   sudo systemctl start yral-ai-chat"
echo "  Stop:    sudo systemctl stop yral-ai-chat"
echo "  Restart: sudo systemctl restart yral-ai-chat"
echo "  Status:  sudo systemctl status yral-ai-chat"
echo "  Logs:    sudo journalctl -u yral-ai-chat -f"
echo ""
echo "App logs location:"
echo "  /root/yral-ai-chat/logs/uvicorn.log"
echo "  /root/yral-ai-chat/logs/uvicorn-error.log"
echo ""

