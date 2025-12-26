#!/usr/bin/env python3
"""
Test script to verify JWT authentication implementation
"""
import asyncio
import sys
import time
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import jwt

from src.auth.jwt_auth import decode_jwt
from src.config import settings


async def test_hs256_token():
    """Test HS256 token verification"""
    print("Testing HS256 token verification...")
    
    # Generate a valid token
    payload = {
        "sub": "test_user_123",
        "iss": settings.jwt_issuer,
        "iat": int(time.time()),
        "exp": int(time.time()) + 3600,
    }
    
    token = jwt.encode(payload, settings.jwt_secret_key, algorithm="HS256")
    print(f"Generated token: {token[:50]}...")
    
    # Verify it
    try:
        decoded = await decode_jwt(token)
        print(f"✓ Token verified successfully!")
        print(f"  User ID: {decoded['sub']}")
        print(f"  Issuer: {decoded['iss']}")
        return True
    except Exception as e:
        print(f"✗ Token verification failed: {e}")
        return False


async def test_expired_token():
    """Test that expired tokens are rejected"""
    print("\nTesting expired token rejection...")
    
    payload = {
        "sub": "test_user_123",
        "iss": settings.jwt_issuer,
        "iat": int(time.time()) - 7200,
        "exp": int(time.time()) - 3600,  # Expired 1 hour ago
    }
    
    token = jwt.encode(payload, settings.jwt_secret_key, algorithm="HS256")
    
    try:
        await decode_jwt(token)
        print("✗ Expired token was accepted (should be rejected)")
        return False
    except Exception as e:
        if "expired" in str(e).lower():
            print("✓ Expired token correctly rejected")
            return True
        else:
            print(f"✗ Unexpected error: {e}")
            return False


async def test_wrong_issuer():
    """Test that tokens with wrong issuer are rejected"""
    print("\nTesting wrong issuer rejection...")
    
    payload = {
        "sub": "test_user_123",
        "iss": "wrong_issuer",
        "iat": int(time.time()),
        "exp": int(time.time()) + 3600,
    }
    
    token = jwt.encode(payload, settings.jwt_secret_key, algorithm="HS256")
    
    try:
        await decode_jwt(token)
        print("✗ Token with wrong issuer was accepted (should be rejected)")
        return False
    except Exception as e:
        if "issuer" in str(e).lower():
            print("✓ Token with wrong issuer correctly rejected")
            return True
        else:
            print(f"✗ Unexpected error: {e}")
            return False


async def test_invalid_signature():
    """Test that tokens with invalid signature are rejected"""
    print("\nTesting invalid signature rejection...")
    
    payload = {
        "sub": "test_user_123",
        "iss": settings.jwt_issuer,
        "iat": int(time.time()),
        "exp": int(time.time()) + 3600,
    }
    
    # Sign with wrong secret
    token = jwt.encode(payload, "wrong_secret_key", algorithm="HS256")
    
    try:
        await decode_jwt(token)
        print("✗ Token with invalid signature was accepted (should be rejected)")
        return False
    except Exception as e:
        if "invalid" in str(e).lower() or "signature" in str(e).lower():
            print("✓ Token with invalid signature correctly rejected")
            return True
        else:
            print(f"✗ Unexpected error: {e}")
            return False


async def main():
    """Run all tests"""
    print("=" * 60)
    print("JWT Authentication Security Tests")
    print("=" * 60)
    print(f"Issuer: {settings.jwt_issuer}")
    print(f"Algorithm: HS256 (using shared secret)")
    print("=" * 60)
    
    results = []
    results.append(await test_hs256_token())
    results.append(await test_expired_token())
    results.append(await test_wrong_issuer())
    results.append(await test_invalid_signature())
    
    print("\n" + "=" * 60)
    print(f"Results: {sum(results)}/{len(results)} tests passed")
    print("=" * 60)
    
    if all(results):
        print("✓ All tests passed! JWT authentication is secure.")
        return 0
    else:
        print("✗ Some tests failed. Please review the implementation.")
        return 1


if __name__ == "__main__":
    exit(asyncio.run(main()))

