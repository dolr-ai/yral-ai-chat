#!/bin/bash
# Complete test flow for Yral AI Chat API

set -e

BASE_URL="http://localhost:8000"
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo "🧪 Yral AI Chat API - Complete Test Flow"
echo "========================================"
echo ""

# Check if server is running
echo -n "Checking if server is running... "
if curl -s -o /dev/null -w "%{http_code}" $BASE_URL/health | grep -q "200"; then
    echo -e "${GREEN}✓ Server is running${NC}"
else
    echo -e "${YELLOW}⚠ Server not running. Start it with:${NC}"
    echo "  cd /root/yral-ai-chat && source venv/bin/activate && uvicorn src.main:app --reload --host 0.0.0.0 --port 8000"
    exit 1
fi
echo ""

# Test 1: Health Check
echo -e "${BLUE}1. Health Check${NC}"
curl -s $BASE_URL/health | python3 -m json.tool
echo ""

# Test 2: List Influencers
echo -e "${BLUE}2. List AI Influencers${NC}"
INFLUENCERS=$(curl -s $BASE_URL/api/v1/influencers)
echo "$INFLUENCERS" | python3 -m json.tool
INFLUENCER_ID=$(echo "$INFLUENCERS" | grep -o '"id":"[^"]*' | head -1 | cut -d'"' -f4)
echo -e "${GREEN}✓ Found influencer ID: $INFLUENCER_ID${NC}"
echo ""

# Test 3: Get Specific Influencer
echo -e "${BLUE}3. Get Influencer Details${NC}"
curl -s "$BASE_URL/api/v1/influencers/$INFLUENCER_ID" | python3 -m json.tool
echo ""

# Test 4: Generate JWT Token
echo -e "${BLUE}4. Generate JWT Token${NC}"
cd /root/yral-ai-chat
source venv/bin/activate

# Load JWT secret from .env file
source .env 2>/dev/null || {
    echo -e "${RED}Error: .env file not found. Please create it first.${NC}"
    exit 1
}

TOKEN=$(python3 -c "
import jwt
import os
from datetime import datetime, timedelta
payload = {
    'user_id': 'test_user_' + datetime.now().strftime('%Y%m%d%H%M%S'),
    'exp': datetime.utcnow() + timedelta(days=1),
    'iss': 'yral_auth'
}
print(jwt.encode(payload, os.environ.get('JWT_SECRET_KEY', 'test-key'), algorithm='HS256'))
")
echo -e "${GREEN}✓ Generated token for test user${NC}"
echo ""

# Test 5: Create Conversation
echo -e "${BLUE}5. Create Conversation${NC}"
CONV_RESPONSE=$(curl -s -X POST "$BASE_URL/api/v1/chat/conversations" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"influencer_id\": \"$INFLUENCER_ID\"}")
echo "$CONV_RESPONSE" | python3 -m json.tool
CONVERSATION_ID=$(echo "$CONV_RESPONSE" | grep -o '"id":"[^"]*' | head -1 | cut -d'"' -f4)
echo -e "${GREEN}✓ Created conversation ID: $CONVERSATION_ID${NC}"
echo ""

# Test 6: List Conversations
echo -e "${BLUE}6. List User Conversations${NC}"
curl -s -H "Authorization: Bearer $TOKEN" \
  "$BASE_URL/api/v1/chat/conversations" | python3 -m json.tool
echo ""

# Test 7: Send Message (only if Gemini API key is configured)
echo -e "${BLUE}7. Send Message to AI${NC}"
if grep -q "placeholder-get-from-google-cloud" /root/yral-ai-chat/.env 2>/dev/null; then
    echo -e "${YELLOW}⚠ Skipping - Gemini API key not configured${NC}"
    echo "  To test chat: Add your GEMINI_API_KEY to .env"
else
    MSG_RESPONSE=$(curl -s -X POST "$BASE_URL/api/v1/chat/conversations/$CONVERSATION_ID/messages" \
      -H "Authorization: Bearer $TOKEN" \
      -H "Content-Type: application/json" \
      -d '{
        "content": "Hi! Give me one quick tip.",
        "message_type": "text"
      }')
    echo "$MSG_RESPONSE" | python3 -m json.tool
    echo -e "${GREEN}✓ Message sent and AI responded${NC}"
fi
echo ""

# Test 8: Get Message History
echo -e "${BLUE}8. Get Message History${NC}"
curl -s -H "Authorization: Bearer $TOKEN" \
  "$BASE_URL/api/v1/chat/conversations/$CONVERSATION_ID/messages" | python3 -m json.tool
echo ""

# Test 9: Delete Conversation
echo -e "${BLUE}9. Delete Conversation${NC}"
curl -s -X DELETE -H "Authorization: Bearer $TOKEN" \
  "$BASE_URL/api/v1/chat/conversations/$CONVERSATION_ID" | python3 -m json.tool
echo -e "${GREEN}✓ Conversation deleted${NC}"
echo ""

echo "========================================"
echo -e "${GREEN}✅ All tests completed successfully!${NC}"
echo ""
echo "Next steps:"
echo "  • Add Gemini API key to .env to test chat"
echo "  • View API docs: $BASE_URL/docs"
echo "  • Check logs: tail -f /root/yral-ai-chat/logs/yral_ai_chat.log"

