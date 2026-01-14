import httpx
from loguru import logger
from src.config import settings

class NotificationService:
    """Service to handle sending notifications to Google Chat"""

    async def send_sentry_notification(self, resource: str, action: str, data: dict):
        """Dispatches notifications to Google Chat (Production only)"""
        
        if settings.environment != "production":
            logger.debug(f"Skipping Sentry notification for {settings.environment} environment")
            return

        if settings.google_chat_webhook_url:
            await self._send_to_google_chat(resource, action, data)
        else:
            logger.debug("Google Chat webhook not configured, skipping notification")

    async def _send_to_google_chat(self, resource: str, action: str, data: dict):
        """Sends a formatted card to Google Chat"""
        try:
            issue = data.get("issue", {})
            title = issue.get("title", "Sentry Alert")
            short_id = issue.get("shortId", "N/A")
            issue_url = issue.get("permalink", "https://sentry.yral.com/")
            
            card = {
                "cardsV2": [{
                    "cardId": "sentry_alert",
                    "card": {
                        "header": {
                            "title": f"Sentry: {resource.capitalize()} {action.capitalize()}",
                            "subtitle": short_id,
                            "imageUrl": "https://sentry.io/_static/1601416489/sentry/images/logos/apple-touch-icon.png"
                        },
                        "sections": [{
                            "widgets": [
                                {"textParagraph": {"text": f"<b>{title}</b>"}},
                                {
                                    "buttonList": {
                                        "buttons": [{
                                            "text": "View in Sentry",
                                            "onClick": {"openLink": {"url": issue_url}}
                                        }]
                                    }
                                }
                            ]
                        }]
                    }
                }]
            }

            async with httpx.AsyncClient() as client:
                response = await client.post(settings.google_chat_webhook_url, json=card)
                if response.status_code != 200:
                    logger.error(f"Failed to send to Google Chat: {response.status_code} {response.text}")
                else:
                    logger.info("Successfully sent notification to Google Chat")
        except Exception as e:
            logger.error(f"Error sending to Google Chat: {e}")

notification_service = NotificationService()
