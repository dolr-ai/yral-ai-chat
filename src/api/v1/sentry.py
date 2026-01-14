import hmac
import hashlib
import json
from fastapi import APIRouter, Request, Header, HTTPException, status, BackgroundTasks
from loguru import logger
from src.config import settings
from src.services.notification_service import notification_service

router = APIRouter(prefix="/sentry", tags=["Sentry Webhooks"])

async def verify_signature(request: Request, secret: str) -> bool:
    """
    Verifies that the request actually came from Sentry by checking the Sentry-Hook-Signature header.
    
    The signature is an HMAC-SHA256 hash of the request body using the Client Secret as the key.
    """
    signature = request.headers.get("Sentry-Hook-Signature")
    if not signature:
        return False
    
    body = await request.body()
    
    expected_signature = hmac.new(
        secret.encode("utf-8"),
        body,
        hashlib.sha256
    ).hexdigest()
    
    return hmac.compare_digest(expected_signature, signature)

@router.post("/webhook")
async def sentry_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    sentry_hook_resource: str = Header(..., alias="Sentry-Hook-Resource"),
    sentry_hook_signature: str = Header(..., alias="Sentry-Hook-Signature")
):
    """
    Endpoint for Sentry webhooks.
    Handles various resources like issue, event_alert, metric_alert, etc.
    """
    if not settings.sentry_webhook_secret:
        logger.error("SENTRY_WEBHOOK_SECRET is not configured")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Webhook secret not configured"
        )

    # Verify signature
    if not await verify_signature(request, settings.sentry_webhook_secret):
        logger.warning(f"Invalid Sentry webhook signature received for resource: {sentry_hook_resource}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid signature"
        )

    try:
        payload = await request.json()
    except json.JSONDecodeError:
        logger.warning("Invalid JSON payload in Sentry webhook")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON"
        )

    action = payload.get("action")
    data = payload.get("data", {})
    
    logger.info(f"Received Sentry webhook: resource={sentry_hook_resource}, action={action}")

    # Triaging based on resource type
    if sentry_hook_resource == "issue":
        issue_id = data.get("issue", {}).get("id")
        issue_title = data.get("issue", {}).get("title")
        logger.info(f"Sentry Issue {action}: {issue_id} - {issue_title}")
        
    elif sentry_hook_resource == "event_alert":
        alert_name = data.get("event", {}).get("title")
        logger.info(f"Sentry Event Alert: {alert_name}")
        
    elif sentry_hook_resource == "metric_alert":
        alert_name = data.get("description_text")
        logger.info(f"Sentry Metric Alert: {alert_name}")
        
    elif sentry_hook_resource == "installation":
        logger.info(f"Sentry Integration {action}")

    # Forward to notifications in the background
    background_tasks.add_task(
        notification_service.send_sentry_notification,
        sentry_hook_resource,
        action or "unknown",
        payload
    )

    # Respond quickly (within 1s) as required by Sentry
    return {"status": "accepted"}
