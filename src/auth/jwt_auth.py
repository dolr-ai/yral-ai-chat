"""
JWT Authentication and validation
"""
import base64
import json
import time

import sentry_sdk
from fastapi import Header, HTTPException
from loguru import logger
from pydantic import BaseModel, ConfigDict

from src.config import settings
from src.models.internal import JWTPayload


class CurrentUser(BaseModel):
    """Current authenticated user"""
    model_config = ConfigDict(from_attributes=True)

    user_id: str
    payload: JWTPayload


def _base64url_decode(input_str: str) -> bytes:
    """Decode a base64url-encoded string, adding padding if necessary"""
    padding = "=" * (-len(input_str) % 4)
    return base64.urlsafe_b64decode(input_str + padding)


def _raise_auth_error(detail: str) -> None:
    """Raise HTTPException for authentication errors"""
    raise HTTPException(
        status_code=401,
        detail=detail,
    )


def decode_jwt(token: str) -> JWTPayload:
    """
    Decode and validate JWT token from auth.yral.com
    
    Args:
        token: JWT token string
        
    Returns:
        Decoded payload
        
    Raises:
        HTTPException: If token is invalid or expired
    """
    try:
        parts = token.split(".")
        if len(parts) != 3:
            _raise_auth_error("Invalid token format")

        header_b64, payload_b64, _signature_b64 = parts

        header_bytes = _base64url_decode(header_b64)
        payload_bytes = _base64url_decode(payload_b64)

        header = json.loads(header_bytes)
        payload = json.loads(payload_bytes)

        logger.debug(f"Decoded JWT header: {header}")

        issuer = payload.get("iss")
        expected_issuer = "https://auth.yral.com"
        if issuer != expected_issuer:
            logger.warning(f"JWT token has invalid issuer: {issuer}")
            _raise_auth_error("Invalid token issuer")

        exp = payload.get("exp")
        if exp is None:
            logger.warning("JWT token missing exp claim")
            _raise_auth_error("Token has expired")

        try:
            exp_int = int(exp)
        except (TypeError, ValueError) as e:
            logger.warning(f"JWT token has invalid exp claim: {exp}")
            raise HTTPException(
                status_code=401,
                detail="Invalid token",
            ) from e

        now = int(time.time())
        if exp_int <= now:
            logger.warning("JWT token expired")
            _raise_auth_error("Token has expired")

        if "sub" not in payload:
            logger.warning("JWT token missing sub claim")
            _raise_auth_error("Invalid token: missing sub")

        return JWTPayload(
            sub=payload["sub"],
            iss=payload.get("iss", ""),
            exp=payload.get("exp", 0),
            iat=payload.get("iat"),
            aud=payload.get("aud"),
            jti=payload.get("jti")
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"JWT decode error: {e}")
        raise HTTPException(
            status_code=401,
            detail="Authentication failed",
        ) from e


async def get_current_user(authorization: str | None = Header(None)) -> CurrentUser:
    """
    FastAPI dependency to get current authenticated user
    
    Args:
        authorization: Authorization header (Bearer token)
        
    Returns:
        CurrentUser object
    """
    if not authorization:
        raise HTTPException(
            status_code=401,
            detail="Missing authorization header"
        )

    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=401,
            detail="Invalid authorization header format. Expected: Bearer <token>"
        )

    token = parts[1]
    
    # Support static monitoring token bypass
    if settings.monitoring_token and token == settings.monitoring_token:
        user_id = "monitoring-bot"
        sentry_sdk.set_user({"id": user_id})
        logger.info(f"Authenticated via static monitoring token: {user_id}")
        return CurrentUser(
            user_id=user_id,
            payload=JWTPayload(
                sub=user_id,
                iss="https://chat.yral.com/health",
                exp=int(time.time()) + 3600  # Mock 1 hour expiry
            )
        )

    payload = decode_jwt(token)

    user_id = payload.sub
    sentry_sdk.set_user({"id": user_id})

    return CurrentUser(
        user_id=user_id,
        payload=payload,
    )


async def get_optional_user(authorization: str | None = Header(None)) -> CurrentUser | None:
    """
    Optional authentication - returns None if not authenticated
    
    Args:
        authorization: Authorization header (Bearer token)
        
    Returns:
        CurrentUser object or None
    """
    if not authorization:
        return None

    try:
        return await get_current_user(authorization)
    except HTTPException:
        return None
