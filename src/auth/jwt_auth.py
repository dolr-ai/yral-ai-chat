"""
JWT Authentication and validation
"""
import jwt
from fastapi import Header, HTTPException
from loguru import logger

from src.config import settings


class CurrentUser:
    """Current authenticated user"""
    def __init__(self, user_id: str, payload: dict):
        self.user_id = user_id
        self.payload = payload


def decode_jwt(token: str) -> dict:
    """
    Decode and validate JWT token
    
    Args:
        token: JWT token string
        
    Returns:
        Decoded payload
        
    Raises:
        HTTPException: If token is invalid or expired
    """
    try:
        # Decode JWT
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
            issuer=settings.jwt_issuer
        )

        # Validate required fields
        if "user_id" not in payload:
            raise HTTPException(
                status_code=401,
                detail="Invalid token: missing user_id"
            )
    except HTTPException:
        # Re-raise HTTPException (like missing user_id) without wrapping
        raise
    except jwt.ExpiredSignatureError as e:
        logger.warning("JWT token expired")
        raise HTTPException(
            status_code=401,
            detail="Token has expired"
        ) from e
    except jwt.InvalidIssuerError as e:
        logger.warning("JWT token has invalid issuer")
        raise HTTPException(
            status_code=401,
            detail="Invalid token issuer"
        ) from e
    except jwt.InvalidTokenError as e:
        logger.warning(f"Invalid JWT token: {e}")
        raise HTTPException(
            status_code=401,
            detail="Invalid token"
        ) from e
    except Exception as e:
        logger.error(f"JWT decode error: {e}")
        raise HTTPException(
            status_code=401,
            detail="Authentication failed"
        ) from e
    else:
        return payload


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
        user_id=payload["user_id"],
        payload=payload
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
