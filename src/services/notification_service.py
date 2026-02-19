from typing import Any

import httpx
from loguru import logger

from src.config import settings


class MetadataPNProvider:
    """Dispatches notifications via the centralized Yral Metadata Server."""

    async def send_notification(
        self,
        user_id: str,
        title: str,
        body: str,
        data: dict[str, Any] | None = None,
    ) -> bool:
        """
        Calls the Metadata Server to send a push notification.
        Endpoint: POST /notifications/{user_id}/send
        """
        if not settings.metadata_url:
            logger.warning("Notification skipped: METADATA_URL not configured")
            return False

        url = f"{settings.metadata_url.rstrip('/')}/notifications/{user_id}/send"
        payload = {
            "data": {
                "title": title,
                "body": body,
                **(data or {})
            }
        }

        headers = {}
        if settings.metadata_auth_token:
            headers["Authorization"] = f"Bearer {settings.metadata_auth_token}"

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(url, json=payload, headers=headers, timeout=10.0)
                if response.status_code == 200:
                    logger.info(f"Notification sent to {user_id} via Metadata Server")
                    return True
                
                logger.error(
                    f"Metadata PNS error for {user_id}: {response.status_code} - {response.text}"
                )
                return False
        except Exception as e:
            logger.error(f"Failed to call Metadata Server for {user_id}: {e}")
            return False


class NotificationService:
    """Central service for application notifications (Push & Google Chat)."""

    def __init__(self, provider: MetadataPNProvider | None = None):
        self.provider = provider or MetadataPNProvider()

    async def send_push_notification(
        self,
        user_id: str,
        title: str,
        body: str,
        data: dict | None = None,
    ) -> bool:
        """Sends a push notification to a user's devices."""
        try:
            return await self.provider.send_notification(user_id, title, body, data)
        except Exception as e:
            logger.error(f"Push notification error: {e}")
            return False

    async def send_sentry_notification(self, resource: str, action: str, data: dict):
        """Dispatches internal alerts to Google Chat (Production only)."""
        if settings.environment != "production" or not settings.google_chat_webhook_url:
            return

        try:
            issue = data.get("issue", {})
            card = {
                "cardsV2": [{
                    "cardId": "sentry_alert",
                    "card": {
                        "header": {
                            "title": f"Sentry: {resource.capitalize()} {action.capitalize()}",
                            "subtitle": issue.get("shortId", "N/A"),
                            "imageUrl": "https://sentry.io/_static/1601416489/sentry/images/logos/apple-touch-icon.png"
                        },
                        "sections": [{
                            "widgets": [
                                {"textParagraph": {"text": f"<b>{issue.get('title', 'Sentry Alert')}</b>"}},
                                {
                                    "buttonList": {
                                        "buttons": [{
                                            "text": "View in Sentry",
                                            "onClick": {"openLink": {"url": issue.get("permalink", "#")}}
                                        }]
                                    }
                                }
                            ]
                        }]
                    }
                }]
            }

            async with httpx.AsyncClient() as client:
                await client.post(settings.google_chat_webhook_url, json=card)
        except Exception as e:
            logger.error(f"Google Chat notification error: {e}")


notification_service = NotificationService()
