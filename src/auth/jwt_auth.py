"""
JWT Authentication and validation
"""
import base64
import json
import time

from fastapi import Header, HTTPException
from loguru import logger


class CurrentUser:
    """Current authenticated user"""

    def __init__(self, user_id: str, payload: dict):
        self.user_id = user_id
        self.payload = payload


def _base64url_decode(input_str: str) -> bytes:
    """Decode a base64url-encoded string, adding padding if necessary."""
    padding = "=" * (-len(input_str) % 4)
    return base64.urlsafe_b64decode(input_str + padding)


def decode_jwt(token: str) -> dict:
    """
    Decode and validate JWT token coming from auth.yral.com.

    This function:
    - base64url decodes the header and payload without verifying the signature
    - validates issuer, expiration, and required claims

    Args:
        token: JWT token string

    Returns:
        Decoded payload

    Raises:
        HTTPException: If token is invalid or expired
    """
    try:
        # Split token into parts
        parts = token.split(".")
        if len(parts) != 3:
            raise HTTPException(
                status_code=401,
                detail="Invalid token format",
            )

        header_b64, payload_b64, _signature_b64 = parts

        # Decode header and payload
        header_bytes = _base64url_decode(header_b64)
        payload_bytes = _base64url_decode(payload_b64)

        header = json.loads(header_bytes)
        payload = json.loads(payload_bytes)

        # Basic structural validation (optional logging)
        logger.debug(f"Decoded JWT header: {header}")

        # Validate issuer
        issuer = payload.get("iss")
        expected_issuer = "https://auth.yral.com"
        if issuer != expected_issuer:
            logger.warning(f"JWT token has invalid issuer: {issuer}")
            raise HTTPException(
                status_code=401,
                detail="Invalid token issuer",
            )

        # Validate expiration
        exp = payload.get("exp")
        if exp is None:
            logger.warning("JWT token missing exp claim")
            raise HTTPException(
                status_code=401,
                detail="Token has expired",
            )

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
            raise HTTPException(
                status_code=401,
                detail="Token has expired",
            )

        # Validate required subject (user identifier)
        if "sub" not in payload:
            logger.warning("JWT token missing sub claim")
            raise HTTPException(
                status_code=401,
                detail="Invalid token: missing sub",
            )

        return payload

    except HTTPException:
        # Re-raise HTTPException without wrapping
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

    # Extract token from "Bearer <token>"
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=401,
            detail="Invalid authorization header format. Expected: Bearer <token>"
        )

    token = parts[1]
    payload = decode_jwt(token)

    return CurrentUser(
        user_id=payload["sub"],
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
