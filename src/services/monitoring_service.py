import asyncio

import httpx
from loguru import logger

from src.config import settings


class MonitoringService:
    """Service to handle active push notifications to monitoring systems like Uptime Kuma"""
    
    def __init__(self):
        self.push_url = settings.uptime_kuma_push_url
        self.google_chat_url = settings.google_chat_webhook_url
        self.interval = 60  # seconds
        self._task = None
        self._client = httpx.AsyncClient(timeout=10.0)

    async def start(self):
        """Start the background heartbeat task and notify Google Chat"""
        if self._task:
            return

        # 1. Start Kuma Push Heartbeat if configured
        if self.push_url:
            logger.info(f"Starting Uptime Kuma heartbeat service (interval: {self.interval}s)")
            self._task = asyncio.create_task(self._run_heartbeat())
        else:
            logger.info("Uptime Kuma Push URL not configured, skipping heartbeat service")

        # 2. Send Startup Notification to Google Chat
        if self.google_chat_url:
            await self.notify_google_chat(
                f"🚀 *{settings.app_name} v{settings.app_version}* started successfully in *{settings.environment}* mode."
            )

    async def notify_google_chat(self, text: str):
        """Send a direct notification to Google Chat"""
        if not self.google_chat_url:
            return

        try:
            response = await self._client.post(
                self.google_chat_url,
                json={"text": text}
            )
            if response.status_code == 200:
                logger.debug("Successfully sent notification to Google Chat")
            else:
                logger.warning(f"Failed to send Google Chat notification (Status: {response.status_code})")
        except Exception as e:
            logger.error(f"Error sending Google Chat notification: {e}")

    async def stop(self):
        """Stop the background heartbeat task"""
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
            logger.info("Uptime Kuma heartbeat service stopped")
        
        await self._client.aclose()

    async def _run_heartbeat(self):
        """Periodically ping the configured push URL"""
        while True:
            try:
                response = await self._client.get(self.push_url)
                if response.status_code == 200:
                    logger.debug("Successfully sent heartbeat to Uptime Kuma")
                else:
                    logger.warning(f"Failed to send heartbeat to Uptime Kuma (Status: {response.status_code})")
            except Exception as e:
                logger.error(f"Error sending heartbeat to Uptime Kuma: {e}")
            
            await asyncio.sleep(self.interval)

monitoring_service = MonitoringService()
