#!/bin/bash
# Setup script for nginx reverse proxy with SSL

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo "🔧 Setting up Nginx Reverse Proxy for Yral AI Chat API"
echo "======================================================"
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo -e "${RED}Error: Please run as root (use sudo)${NC}"
    exit 1
fi

# Get domain name
read -p "Enter your domain name [chat.yral.com]: " DOMAIN_NAME

# Default to chat.yral.com if no input
if [ -z "$DOMAIN_NAME" ]; then
    DOMAIN_NAME="chat.yral.com"
fi

echo ""
echo -e "${YELLOW}Domain: ${DOMAIN_NAME}${NC}"
echo ""

# Check if nginx is installed
if ! command -v nginx &> /dev/null; then
    echo "Installing nginx..."
    apt-get update
    apt-get install -y nginx
else
    echo -e "${GREEN}✓ Nginx is already installed${NC}"
fi

# Check if certbot is installed
if ! command -v certbot &> /dev/null; then
    echo "Installing certbot..."
    apt-get install -y certbot python3-certbot-nginx
else
    echo -e "${GREEN}✓ Certbot is already installed${NC}"
fi

# Create nginx config directory if it doesn't exist
mkdir -p /etc/nginx/sites-available
mkdir -p /etc/nginx/sites-enabled

# Copy and configure nginx config
echo "Configuring nginx..."
CONFIG_FILE="/etc/nginx/sites-available/yral-ai-chat.conf"
cp /root/yral-ai-chat/nginx/yral-ai-chat.conf "$CONFIG_FILE"

# Replace domain name in config
sed -i "s/chat.yral.com/$DOMAIN_NAME/g" "$CONFIG_FILE"
sed -i "s/www.chat.yral.com/www.$DOMAIN_NAME/g" "$CONFIG_FILE"

# Create symlink
if [ -f "/etc/nginx/sites-enabled/yral-ai-chat.conf" ]; then
    echo -e "${YELLOW}⚠ Config already exists in sites-enabled, skipping symlink${NC}"
else
    ln -s "$CONFIG_FILE" /etc/nginx/sites-enabled/yral-ai-chat.conf
    echo -e "${GREEN}✓ Created symlink${NC}"
fi

# Test nginx configuration
echo ""
echo "Testing nginx configuration..."
if nginx -t; then
    echo -e "${GREEN}✓ Nginx configuration is valid${NC}"
else
    echo -e "${RED}✗ Nginx configuration test failed${NC}"
    exit 1
fi

# Start nginx
echo ""
echo "Starting nginx..."
systemctl restart nginx
systemctl enable nginx
echo -e "${GREEN}✓ Nginx started and enabled${NC}"

# Check if FastAPI app is running
echo ""
echo "Checking if FastAPI app is running on port 8000..."
if curl -s http://localhost:8000/health > /dev/null 2>&1; then
    echo -e "${GREEN}✓ FastAPI app is running${NC}"
else
    echo -e "${YELLOW}⚠ FastAPI app is not running on port 8000${NC}"
    echo "   Start it with: cd /root/yral-ai-chat && source venv/bin/activate && uvicorn src.main:app --host 0.0.0.0 --port 8000"
fi

# Setup SSL certificate
echo ""
echo "=========================================="
echo "SSL Certificate Setup"
echo "=========================================="
echo ""
read -p "Do you want to set up SSL certificate with Let's Encrypt now? (y/n): " SETUP_SSL

if [ "$SETUP_SSL" = "y" ] || [ "$SETUP_SSL" = "Y" ]; then
    echo ""
    echo "Setting up SSL certificate with Let's Encrypt..."
    echo "This will require email verification and domain validation."
    echo ""
    
    certbot --nginx -d "$DOMAIN_NAME" -d "www.$DOMAIN_NAME" --non-interactive --agree-tos --email admin@"$DOMAIN_NAME" || {
        echo ""
        echo -e "${YELLOW}⚠ Certbot setup failed or requires manual intervention${NC}"
        echo "You can run it manually with:"
        echo "  sudo certbot --nginx -d $DOMAIN_NAME -d www.$DOMAIN_NAME"
    }
else
    echo ""
    echo -e "${YELLOW}⚠ SSL certificate not set up${NC}"
    echo "To set it up later, run:"
    echo "  sudo certbot --nginx -d $DOMAIN_NAME -d www.$DOMAIN_NAME"
fi

# Check firewall
echo ""
echo "=========================================="
echo "Firewall Configuration"
echo "=========================================="
if command -v ufw &> /dev/null; then
    echo "Checking UFW firewall..."
    if ufw status | grep -q "Status: active"; then
        echo "Opening ports 80 and 443..."
        ufw allow 80/tcp
        ufw allow 443/tcp
        echo -e "${GREEN}✓ Firewall rules added${NC}"
    else
        echo -e "${YELLOW}⚠ UFW is not active${NC}"
    fi
elif command -v firewall-cmd &> /dev/null; then
    echo "Checking firewalld..."
    firewall-cmd --permanent --add-service=http
    firewall-cmd --permanent --add-service=https
    firewall-cmd --reload
    echo -e "${GREEN}✓ Firewall rules added${NC}"
else
    echo -e "${YELLOW}⚠ No firewall detected. Make sure ports 80 and 443 are open${NC}"
fi

# Final summary
echo ""
echo "=========================================="
echo -e "${GREEN}Setup Complete!${NC}"
echo "=========================================="
echo ""
echo "Next steps:"
echo "1. Ensure your domain DNS points to this server's IP"
echo "2. Make sure FastAPI app is running:"
echo "   cd /root/yral-ai-chat && source venv/bin/activate"
echo "   uvicorn src.main:app --host 0.0.0.0 --port 8000"
echo ""
if [ "$SETUP_SSL" != "y" ] && [ "$SETUP_SSL" != "Y" ]; then
    echo "3. Set up SSL certificate:"
    echo "   sudo certbot --nginx -d $DOMAIN_NAME -d www.$DOMAIN_NAME"
    echo ""
fi
echo "4. Test your API:"
echo "   curl https://$DOMAIN_NAME/health"
echo ""
echo "5. Update your .env file:"
echo "   CORS_ORIGINS=https://$DOMAIN_NAME,https://www.$DOMAIN_NAME"
echo "   MEDIA_BASE_URL=https://$DOMAIN_NAME/media"
echo ""
echo "Nginx config location: $CONFIG_FILE"
echo "Nginx logs: /var/log/nginx/yral-ai-chat-*.log"
echo ""




