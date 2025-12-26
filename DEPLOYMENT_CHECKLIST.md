# JWT Authentication Security Update - Deployment Checklist

## ⚠️ CRITICAL: Breaking Changes

This update introduces **signature verification** for JWT tokens. This is a **breaking change** that requires coordination with your auth service.

## Pre-Deployment Checklist

### 1. **Environment Variables** ✅
Ensure these are set correctly in your staging/production environment:

```bash
# Required - Must match auth service
JWT_SECRET_KEY=<your-shared-secret-key>  # Must match auth.yral.com if using HS256
JWT_ISSUER=https://auth.yral.com         # Must match 'iss' claim in tokens

# Optional - Only if tokens include 'aud' claim
JWT_AUDIENCE=yral-ai-chat

# Optional - Only if JWKS is at non-standard location
JWT_JWKS_URL=https://auth.yral.com/.well-known/jwks.json
```

### 2. **Verify Token Format** 🔍
Before deploying, verify that tokens from `auth.yral.com`:
- Include `iss: "https://auth.yral.com"` claim
- Are signed with either:
  - **HS256** (shared secret) - requires matching `JWT_SECRET_KEY`
  - **RS256/ES256** (public key) - requires accessible JWKS endpoint

### 3. **Test with Real Token** 🧪
Test with an actual token from your auth service:
```bash
# Decode a real token to check its structure
python adhoc/decode_jwt.py <real_token>

# Verify it works with the new implementation
python adhoc/test_jwt_auth.py
```

### 4. **JWKS Endpoint Check** 🌐
If using RS256/ES256, verify JWKS is accessible:
```bash
curl https://auth.yral.com/.well-known/jwks.json
```

If it returns 404 or is not accessible, the service will fall back to HS256.

### 5. **Coordinate with Auth Service** 🤝
- **If using HS256**: Ensure `JWT_SECRET_KEY` matches between services
- **If using RS256/ES256**: Ensure JWKS endpoint is publicly accessible
- **If changing issuer**: Update both services simultaneously

## Deployment Steps

### Staging
1. ✅ Update environment variables in staging
2. ✅ Deploy code
3. ✅ Monitor logs for authentication errors
4. ✅ Test with real user tokens
5. ✅ Verify signature verification is working

### Production
1. ✅ Complete staging validation
2. ✅ Update environment variables in production
3. ✅ Deploy during low-traffic window
4. ✅ Monitor authentication success rate
5. ✅ Have rollback plan ready

## Rollback Plan

If authentication breaks after deployment:

1. **Quick Fix**: Revert to previous commit
2. **Root Cause**: Check if:
   - `JWT_SECRET_KEY` doesn't match auth service
   - `JWT_ISSUER` doesn't match token claims
   - JWKS endpoint is unreachable (for RS256/ES256)

## What Changed

### Security Improvements ✅
- ✅ **Signature verification** - Tokens are now cryptographically verified
- ✅ **Algorithm validation** - Prevents algorithm confusion attacks
- ✅ **JWKS support** - Automatic public key fetching for RS256/ES256
- ✅ **Clock skew tolerance** - 60 second buffer for expiration checks
- ✅ **Token size limits** - Prevents DoS attacks

### Breaking Changes ⚠️
- ⚠️ **Signature verification is now required** - Invalid signatures will be rejected
- ⚠️ **Default issuer changed** - From `yral_auth` to `https://auth.yral.com`
- ⚠️ **Stricter validation** - Missing claims will cause authentication to fail

## Monitoring

After deployment, monitor:
- Authentication success/failure rates
- Error logs for JWT-related issues
- Response times (JWKS fetching adds ~50-100ms on first request)

## Support

If you encounter issues:
1. Check application logs: `tail -f logs/yral_ai_chat.log`
2. Look for JWT-related warnings/errors
3. Verify environment variables are set correctly
4. Test with `adhoc/test_jwt_auth.py`

