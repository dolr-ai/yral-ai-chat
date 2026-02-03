from abc import ABC, abstractmethod
from typing import Any

import httpx
from loguru import logger

from src.config import settings


class PushNotificationProvider(ABC):
    """Base class for push notification providers"""

    @abstractmethod
    async def send_notification(
        self,
        user_id: str,
        title: str,
        body: str,
        data: dict[str, Any] | None = None,
    ) -> bool:
        """Send a push notification"""


class MockPNProvider(PushNotificationProvider):
    """Mock provider for development and testing"""

    async def send_notification(
        self,
        user_id: str,
        title: str,
        body: str,
        data: dict[str, Any] | None = None,
    ) -> bool:
        logger.info(
            f"[MockPN] Sending notification to user {user_id}: "
            f"title='{title}', body='{body}', data={data}"
        )
        return True


class NotificationService:
    """Service to handle sending notifications (Google Chat & Push)"""

    def __init__(self, pn_provider: PushNotificationProvider | None = None):
        self.pn_provider = pn_provider or MockPNProvider()

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

    async def send_push_notification(
        self,
        user_id: str,
        title: str,
        body: str,
        data: dict | None = None,
    ):
        """
        Send push notification to user's device via configured provider
        
        Args:
            user_id: User to send notification to
            title: Notification title
            body: Notification body text
            data: Additional data payload (conversation_id, message_id, etc.)
        """
        try:
            success = await self.pn_provider.send_notification(
                user_id=user_id,
                title=title,
                body=body,
                data=data
            )
            if not success:
                logger.warning(f"Push notification failed for user {user_id}")
            return success
        except Exception as e:
            logger.error(f"Error sending push notification: {e}")
            return False


notification_service = NotificationService()
