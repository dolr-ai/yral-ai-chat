#!/usr/bin/env python3
"""
Check what algorithm auth.yral.com is using
"""
import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import asyncio
import httpx


async def check_jwks():
    """Check if JWKS endpoint exists"""
    print("Checking JWKS endpoint...")
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get("https://auth.yral.com/.well-known/jwks.json")
            if response.status_code == 200:
                jwks = response.json()
                print("✓ JWKS endpoint found!")
                print(f"  Keys available: {len(jwks.get('keys', []))}")
                for key in jwks.get('keys', []):
                    alg = key.get('alg', 'unknown')
                    kty = key.get('kty', 'unknown')
                    kid = key.get('kid', 'unknown')
                    print(f"  - Algorithm: {alg}, Key Type: {kty}, Key ID: {kid}")
                return True, jwks
            else:
                print(f"✗ JWKS endpoint returned status {response.status_code}")
                return False, None
    except httpx.HTTPError as e:
        print(f"✗ Could not reach JWKS endpoint: {e}")
        return False, None
    except Exception as e:
        print(f"✗ Error checking JWKS: {e}")
        return False, None


async def check_openid_config():
    """Check OpenID Connect configuration"""
    print("\nChecking OpenID Connect configuration...")
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get("https://auth.yral.com/.well-known/openid-configuration")
            if response.status_code == 200:
                config = response.json()
                print("✓ OpenID Connect configuration found!")
                print(f"  Issuer: {config.get('issuer', 'unknown')}")
                print(f"  JWKS URI: {config.get('jwks_uri', 'unknown')}")
                return True, config
            else:
                print(f"✗ OpenID Connect config returned status {response.status_code}")
                return False, None
    except httpx.HTTPError as e:
        print(f"✗ Could not reach OpenID Connect endpoint: {e}")
        return False, None
    except Exception as e:
        print(f"✗ Error checking OpenID Connect: {e}")
        return False, None


async def main():
    """Check auth service configuration"""
    print("=" * 60)
    print("Auth Service Configuration Check")
    print("=" * 60)
    
    # Check OpenID Connect config first
    oidc_ok, oidc_config = await check_openid_config()
    
    # Check JWKS
    jwks_ok, jwks = await check_jwks()
    
    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    
    if jwks_ok:
        print("✓ Auth service uses RS256/ES256 (public key cryptography)")
        print("  → Your implementation will use JWKS for verification")
        print("  → No JWT_SECRET_KEY needed for RS256/ES256 tokens")
        print("  → Make sure JWKS endpoint is accessible from your server")
    elif oidc_ok:
        jwks_uri = oidc_config.get('jwks_uri', '')
        print(f"⚠ OpenID Connect found but JWKS not accessible")
        print(f"  JWKS URI: {jwks_uri}")
        print("  → Check if JWKS endpoint is publicly accessible")
    else:
        print("✗ No JWKS endpoint found")
        print("  → Auth service likely uses HS256 (shared secret)")
        print("  → You'll need JWT_SECRET_KEY to match auth service")
        print("  → Check GitHub secrets for the correct secret key")
    
    print("\n" + "=" * 60)
    print("GitHub Secrets to Check:")
    print("=" * 60)
    print("Based on the secrets shown, look for:")
    print("  - JWT_SECRET_KEY (for HS256)")
    print("  - AUTH_JWT_ES256_SIGNING_SECRET_KEY_PEM (for ES256 - but this is private key)")
    print("  - AUTH_SESSION_COOKIE_SIGNING_SECRET_KEY (might be for sessions)")
    print("\nNote: If using ES256, you DON'T need the secret key - JWKS will be used instead")


if __name__ == "__main__":
    asyncio.run(main())


