"""
JWT Authentication and validation with signature verification
"""
import base64
import json
import time
from functools import lru_cache
from typing import Optional

import httpx
import jwt
from fastapi import Header, HTTPException
from jose import jwk as jose_jwk
from loguru import logger

from src.config import settings


class CurrentUser:
    """Current authenticated user"""

    def __init__(self, user_id: str, payload: dict):
        self.user_id = user_id
        self.payload = payload


# JWKS cache
_jwks_cache: Optional[dict] = None
_jwks_cache_time: float = 0
JWKS_CACHE_TTL = 3600  # 1 hour cache


def _get_jwks_url() -> str:
    """Get JWKS URL from issuer or configured URL"""
    if settings.jwt_jwks_url:
        return settings.jwt_jwks_url
    
    # Default to standard OIDC JWKS endpoint
    issuer = settings.jwt_issuer.rstrip("/")
    return f"{issuer}/.well-known/jwks.json"


async def _fetch_jwks() -> Optional[dict]:
    """Fetch JWKS from auth server with caching"""
    global _jwks_cache, _jwks_cache_time
    
    now = time.time()
    if _jwks_cache and (now - _jwks_cache_time) < JWKS_CACHE_TTL:
        return _jwks_cache
    
    try:
        jwks_url = _get_jwks_url()
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(jwks_url)
            response.raise_for_status()
            _jwks_cache = response.json()
            _jwks_cache_time = now
            logger.info(f"Fetched JWKS from {jwks_url}")
            return _jwks_cache
    except httpx.HTTPError as e:
        logger.warning(f"Could not fetch JWKS from {_get_jwks_url()}: {e}")
        if _jwks_cache:
            logger.warning("Using cached JWKS due to fetch failure")
            return _jwks_cache
        return None
    except Exception as e:
        logger.error(f"Error fetching JWKS: {e}", exc_info=True)
        if _jwks_cache:
            logger.warning("Using cached JWKS due to fetch failure")
            return _jwks_cache
        return None


def _get_public_key_from_jwks(jwks: dict, kid: Optional[str]) -> tuple[dict, str]:
    """Get public key from JWKS by kid. Returns (key_data, algorithm)"""
    if not jwks.get("keys"):
        raise HTTPException(status_code=503, detail="Invalid JWKS format")
    
    # Find matching key
    for key in jwks["keys"]:
        if kid and key.get("kid") == kid:
            alg = key.get("alg", "RS256")
            return key, alg
        elif not kid and len(jwks["keys"]) == 1:
            # If no kid specified and only one key, use it
            alg = jwks["keys"][0].get("alg", "RS256")
            return jwks["keys"][0], alg
    
    raise HTTPException(status_code=401, detail="Unable to find appropriate key")


def _jwk_to_pem(jwk: dict) -> str:
    """Convert JWK to PEM format using python-jose"""
    try:
        # Construct the key
        key = jose_jwk.construct(jwk)
        return key.to_pem().decode('utf-8')
    except Exception as e:
        logger.error(f"Error converting JWK to PEM: {e}")
        raise HTTPException(status_code=503, detail="Invalid key format") from e


async def decode_jwt(token: str) -> dict:
    """
    Decode and validate JWT token with signature verification.
    
    Supports:
    - RS256/ES256 via JWKS (preferred for OAuth/OIDC)
    - HS256 with shared secret (fallback)
    
    Args:
        token: JWT token string
    
    Returns:
        Decoded payload
    
    Raises:
        HTTPException: If token is invalid or expired
    """
    try:
        # Validate token format
        parts = token.split(".")
        if len(parts) != 3:
            raise HTTPException(status_code=401, detail="Invalid token format")
        
        # Decode header to get algorithm and kid
        try:
            header_b64 = parts[0]
            # Add padding if needed
            padding = "=" * (-len(header_b64) % 4)
            header_bytes = base64.urlsafe_b64decode(header_b64 + padding)
            header = json.loads(header_bytes)
        except Exception as e:
            raise HTTPException(status_code=401, detail="Invalid token format") from e
        
        alg = header.get("alg")
        kid = header.get("kid")
        
        # CRITICAL: Validate algorithm to prevent algorithm confusion attacks
        if alg not in ["RS256", "ES256", "ES384", "ES512", "HS256"]:
            logger.warning(f"Rejected token with unsupported algorithm: {alg}")
            raise HTTPException(status_code=401, detail="Invalid token")
        
        # Try JWKS first (for RS256/ES256)
        if alg in ["RS256", "ES256", "ES384", "ES512"]:
            jwks = await _fetch_jwks()
            if jwks:
                try:
                    jwk, key_alg = _get_public_key_from_jwks(jwks, kid)
                    public_key_pem = _jwk_to_pem(jwk)
                    
                    # Verify and decode with PyJWT
                    payload = jwt.decode(
                        token,
                        public_key_pem,
                        algorithms=[alg],  # Only allow the algorithm from header
                        issuer=settings.jwt_issuer,
                        audience=settings.jwt_audience if settings.jwt_audience else None,
                        options={
                            "verify_signature": True,
                            "verify_exp": True,
                            "verify_iss": True,
                            "verify_aud": bool(settings.jwt_audience),
                            "require_exp": True,
                            "require_iss": True,
                        },
                        leeway=60,  # 60 seconds clock skew tolerance
                    )
                    
                    # Additional validations
                    if "sub" not in payload:
                        raise HTTPException(status_code=401, detail="Invalid token")
                    
                    # Validate nbf (not before) if present
                    if "nbf" in payload:
                        nbf = int(payload["nbf"])
                        now = int(time.time())
                        if nbf > now + 60:  # Allow 60s clock skew
                            raise HTTPException(status_code=401, detail="Token not yet valid")
                    
                    return payload
                except jwt.ExpiredSignatureError:
                    raise HTTPException(status_code=401, detail="Token has expired")
                except jwt.InvalidIssuerError:
                    raise HTTPException(status_code=401, detail="Invalid token issuer")
                except jwt.InvalidAudienceError:
                    raise HTTPException(status_code=401, detail="Invalid token audience")
                except jwt.InvalidSignatureError:
                    logger.warning("JWT signature verification failed")
                    raise HTTPException(status_code=401, detail="Invalid token")
                except jwt.DecodeError as e:
                    logger.warning(f"JWT decode error: {e}")
                    raise HTTPException(status_code=401, detail="Invalid token")
            else:
                logger.warning("JWKS not available, cannot verify RS256/ES256 token")
                raise HTTPException(status_code=503, detail="Authentication service unavailable")
        
        # Fallback to HS256 with shared secret
        elif alg == "HS256":
            try:
                payload = jwt.decode(
                    token,
                    settings.jwt_secret_key,
                    algorithms=["HS256"],  # Explicitly specify algorithm
                    issuer=settings.jwt_issuer,
                    audience=settings.jwt_audience if settings.jwt_audience else None,
                    options={
                        "verify_signature": True,
                        "verify_exp": True,
                        "verify_iss": True,
                        "verify_aud": bool(settings.jwt_audience),
                        "require_exp": True,
                        "require_iss": True,
                    },
                    leeway=60,  # 60 seconds clock skew tolerance
                )
                
                if "sub" not in payload:
                    raise HTTPException(status_code=401, detail="Invalid token")
                
                # Validate nbf if present
                if "nbf" in payload:
                    nbf = int(payload["nbf"])
                    now = int(time.time())
                    if nbf > now + 60:
                        raise HTTPException(status_code=401, detail="Token not yet valid")
                
                return payload
            except jwt.ExpiredSignatureError:
                raise HTTPException(status_code=401, detail="Token has expired")
            except jwt.InvalidIssuerError:
                raise HTTPException(status_code=401, detail="Invalid token issuer")
            except jwt.InvalidAudienceError:
                raise HTTPException(status_code=401, detail="Invalid token audience")
            except jwt.InvalidSignatureError:
                logger.warning("JWT signature verification failed (HS256)")
                raise HTTPException(status_code=401, detail="Invalid token")
            except jwt.DecodeError as e:
                logger.warning(f"JWT decode error: {e}")
                raise HTTPException(status_code=401, detail="Invalid token")
        
        else:
            raise HTTPException(status_code=401, detail="Invalid token")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"JWT decode error: {e}", exc_info=True)
        raise HTTPException(status_code=401, detail="Authentication failed") from e


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
            detail="Invalid authorization header format"
        )
    
    token = parts[1]
    
    # Validate token size to prevent DoS attacks
    if len(token) > 8192:
        raise HTTPException(status_code=401, detail="Invalid token")
    
    payload = await decode_jwt(token)
    
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
