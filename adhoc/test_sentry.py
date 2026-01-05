#!/usr/bin/env python3
"""
Simple script to test Sentry integration with a division by zero error
Usage: python adhoc/test_sentry.py
"""
import os
import sys

# Add parent directory to path to import src modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import sentry_sdk
from loguru import logger

from src.config import settings


def init_sentry():
    """Initialize Sentry SDK"""
    if not settings.sentry_dsn:
        logger.warning("SENTRY_DSN not set - Sentry will not be initialized")
        return False

    # Validate DSN format (basic check)
    dsn = settings.sentry_dsn
    if not dsn.startswith("http"):
        logger.error(f"Invalid DSN format - should start with http:// or https://")
        logger.error(f"DSN (masked): {dsn[:20]}...")
        return False

    try:
        # Add before_send hook to verify events are being processed
        def before_send(event, hint):
            event_id = event.get('event_id', 'unknown')
            event_type = event.get('type', 'unknown')
            level = event.get('level', 'unknown')
            logger.info(f"📤 Sentry event being sent: {event_id}")
            logger.info(f"   Type: {event_type}, Level: {level}")
            if 'exception' in event:
                exc_type = event['exception'].get('values', [{}])[0].get('type', 'unknown')
                logger.info(f"   Exception: {exc_type}")
            return event  # Return event to send it, or None to drop it
        
        # Patch httpx at multiple levels to catch all HTTP requests
        try:
            import httpx
            
            # Helper to log HTTP requests
            def log_http_request(method, url, is_async=False):
                logger.info(f"🌐 HTTP {method} to: {url}{' (async)' if is_async else ''}")
            
            def log_http_response(response, is_async=False):
                logger.info(f"✅ HTTP Response: {response.status_code} {response.reason_phrase}{' (async)' if is_async else ''}")
                if response.status_code >= 400:
                    try:
                        logger.error(f"   Response body: {response.text[:500]}")
                    except:
                        logger.error(f"   Could not read response body")
            
            # Patch Client.request (sync)
            original_sync_request = httpx.Client.request
            def logged_sync_request(self, *args, **kwargs):
                method = kwargs.get('method', args[0] if args else 'GET')
                url = kwargs.get('url', args[1] if len(args) > 1 else 'unknown')
                log_http_request(method, url, False)
                try:
                    response = original_sync_request(self, *args, **kwargs)
                    log_http_response(response, False)
                    return response
                except Exception as e:
                    logger.error(f"❌ HTTP Request failed: {type(e).__name__}: {e}")
                    raise
            httpx.Client.request = logged_sync_request
            
            # Patch AsyncClient.request (async)
            original_async_request = httpx.AsyncClient.request
            async def logged_async_request(self, *args, **kwargs):
                method = kwargs.get('method', args[0] if args else 'GET')
                url = kwargs.get('url', args[1] if len(args) > 1 else 'unknown')
                log_http_request(method, url, True)
                try:
                    response = await original_async_request(self, *args, **kwargs)
                    log_http_response(response, True)
                    return response
                except Exception as e:
                    logger.error(f"❌ HTTP Request failed: {type(e).__name__}: {e}")
                    raise
            httpx.AsyncClient.request = logged_async_request
            
            # Also patch httpx.post, httpx.get, etc. (module-level functions)
            original_post = httpx.post
            def logged_post(*args, **kwargs):
                url = kwargs.get('url', args[0] if args else 'unknown')
                log_http_request('POST', url, False)
                try:
                    response = original_post(*args, **kwargs)
                    log_http_response(response, False)
                    return response
                except Exception as e:
                    logger.error(f"❌ HTTP POST failed: {type(e).__name__}: {e}")
                    raise
            httpx.post = logged_post
            
            # Patch httpx.request (generic request function)
            original_request = httpx.request
            def logged_request(*args, **kwargs):
                method = kwargs.get('method', args[0] if args else 'GET')
                url = kwargs.get('url', args[1] if len(args) > 1 else 'unknown')
                log_http_request(method, url, False)
                try:
                    response = original_request(*args, **kwargs)
                    log_http_response(response, False)
                    return response
                except Exception as e:
                    logger.error(f"❌ HTTP Request failed: {type(e).__name__}: {e}")
                    raise
            httpx.request = logged_request
            
            logger.info("✅ HTTP request logging enabled (Client, AsyncClient, post, request)")
            
            # Also try patching urllib and requests (in case Sentry uses those)
            try:
                import urllib.request
                original_urlopen = urllib.request.urlopen
                def logged_urlopen(*args, **kwargs):
                    url = args[0] if args else 'unknown'
                    logger.info(f"🌐 urllib.request.urlopen to: {url}")
                    try:
                        response = original_urlopen(*args, **kwargs)
                        logger.info(f"✅ urllib Response: {response.status if hasattr(response, 'status') else 'unknown'}")
                        return response
                    except Exception as e:
                        logger.error(f"❌ urllib Request failed: {type(e).__name__}: {e}")
                        raise
                urllib.request.urlopen = logged_urlopen
                logger.info("✅ urllib.request logging enabled")
            except Exception as e:
                logger.debug(f"Could not enable urllib logging: {e}")
            
            try:
                import requests  # type: ignore
                original_requests_post = requests.post
                def logged_requests_post(*args, **kwargs):
                    url = args[0] if args else kwargs.get('url', 'unknown')
                    logger.info(f"🌐 requests.post to: {url}")
                    try:
                        response = original_requests_post(*args, **kwargs)
                        logger.info(f"✅ requests Response: {response.status_code} {response.reason}")
                        if response.status_code >= 400:
                            logger.error(f"   Response body: {response.text[:500]}")
                        return response
                    except Exception as e:
                        logger.error(f"❌ requests POST failed: {type(e).__name__}: {e}")
                        raise
                requests.post = logged_requests_post
                logger.info("✅ requests.post logging enabled")
            except ImportError:
                logger.debug("requests library not installed")
            except Exception as e:
                logger.debug(f"Could not enable requests logging: {e}")
                
        except Exception as e:
            logger.warning(f"Could not enable HTTP logging: {e}")
            import traceback
            logger.warning(traceback.format_exc())
        
        # Try using synchronous transport to see if that helps
        from sentry_sdk.transport import HttpTransport
        
        class LoggingHttpTransport(HttpTransport):
            """Custom transport that logs HTTP requests and responses"""
            def _send_request(self, body, headers, endpoint_type=None, envelope=None):
                """Override to log HTTP requests and responses - matches parent signature"""
                # Get endpoint URL from the transport's auth
                endpoint_url = getattr(self._auth, 'dsn', None)
                if endpoint_url:
                    endpoint_url = str(endpoint_url).split('@')[1] if '@' in str(endpoint_url) else str(endpoint_url)
                else:
                    endpoint_url = "unknown"
                
                logger.info(f"🌐 Transport: Sending request")
                logger.info(f"   Endpoint: {endpoint_url}")
                logger.info(f"   Endpoint type: {endpoint_type}")
                logger.info(f"   Body size: {len(body)} bytes")
                logger.info(f"   Headers: {list(headers.keys())}")
                
                try:
                    # Call parent method with correct signature
                    super()._send_request(body, headers, endpoint_type=endpoint_type, envelope=envelope)
                    logger.info(f"✅ Transport: Request sent successfully (no exception raised)")
                except Exception as e:
                    logger.error(f"❌ Transport: Request failed: {type(e).__name__}: {e}")
                    import traceback
                    logger.error(traceback.format_exc())
                    raise
            
            def _request(self, method, endpoint_type, body, headers):
                """Override to capture actual HTTP response status codes"""
                try:
                    response = super()._request(method, endpoint_type, body, headers)
                    status = getattr(response, 'status', getattr(response, 'status_code', 'unknown'))
                    logger.info(f"📡 HTTP Response: {status}")
                    if status != 200:
                        logger.warning(f"⚠️  Non-200 status code: {status}")
                        # Try to get response body for error details
                        try:
                            if hasattr(response, 'read'):
                                body_text = response.read()
                                logger.warning(f"   Response body: {body_text[:500]}")
                        except:
                            pass
                    return response
                except Exception as e:
                    logger.error(f"❌ HTTP Request exception: {type(e).__name__}: {e}")
                    raise
        
        sentry_sdk.init(
            dsn=dsn,
            environment=settings.environment or "development",
            traces_sample_rate=settings.sentry_traces_sample_rate,
            profiles_sample_rate=settings.sentry_profiles_sample_rate,
            release=settings.sentry_release,
            send_default_pii=True,
            # Remove FastApiIntegration for standalone script - not needed
            integrations=[],  # Add only relevant integrations if needed
            debug=True,  # Enable debug mode to see detailed Sentry logs
            before_send=before_send,  # Add hook to verify events
            max_breadcrumbs=50,  # Maximum number of breadcrumbs
            shutdown_timeout=10,  # Time to wait for events to be sent on shutdown
            transport=LoggingHttpTransport,  # Use custom transport with logging
        )
        logger.info(f"Sentry initialized for environment: {settings.environment}")
        logger.info(f"DSN endpoint: {dsn.split('@')[1].split('/')[0] if '@' in dsn else 'unknown'}")
        return True
    except Exception as e:
        logger.error(f"Failed to initialize Sentry: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False


def trigger_division_by_zero():
    """Trigger a division by zero error to test Sentry"""
    logger.info("About to trigger division by zero error...")
    sentry_sdk.add_breadcrumb(
        category="test",
        message="About to trigger division by zero error",
        level="info"
    )
    
    # Add some context using the modern Sentry SDK API
    scope = sentry_sdk.get_current_scope()
    scope.set_tag("test_type", "division_by_zero")
    scope.set_context("test_info", {
        "script": "test_sentry.py",
        "purpose": "Testing Sentry error tracking"
    })
    
    # Trigger the error
    numerator = 10
    denominator = 0
    sentry_sdk.add_breadcrumb(
        category="test",
        message="Performing division operation",
        level="info",
        data={"numerator": numerator, "denominator": denominator}
    )
    result = numerator / denominator  # This will raise ZeroDivisionError
    return result


if __name__ == "__main__":
    logger.info("Starting Sentry test script...")
    
    logger.info(f"Environment: {settings.environment}")
    logger.info(f"Sentry DSN configured: {bool(settings.sentry_dsn)}")
    
    # Initialize Sentry FIRST (before adding breadcrumbs)
    sentry_initialized = init_sentry()
    
    if not sentry_initialized:
        logger.error("Sentry not initialized - please set SENTRY_DSN in your .env file")
        sys.exit(1)
    
    # NOW add breadcrumbs after Sentry is initialized
    sentry_sdk.add_breadcrumb(
        category="script",
        message="Starting Sentry test script",
        level="info"
    )
    
    sentry_sdk.add_breadcrumb(
        category="config",
        message=f"Environment: {settings.environment}",
        level="info",
        data={"environment": settings.environment}
    )
    
    sentry_sdk.add_breadcrumb(
        category="config",
        message=f"Sentry DSN configured: {bool(settings.sentry_dsn)}",
        level="info"
    )
    
    sentry_sdk.add_breadcrumb(
        category="sentry",
        message="Sentry initialization completed",
        level="info",
        data={"initialized": sentry_initialized}
    )
    
    try:
        trigger_division_by_zero()
    except ZeroDivisionError as e:
        logger.error(f"Division by zero error caught: {e}")
        sentry_sdk.add_breadcrumb(
            category="error",
            message="Division by zero error caught",
            level="error",
            data={"exception_type": type(e).__name__}
        )
        # The error is automatically captured by Sentry when the exception is raised
        # No need to manually capture it again (would cause deduplication)
        logger.info("Error queued for Sentry, flushing...")
        sentry_sdk.add_breadcrumb(
            category="sentry",
            message="Error queued for Sentry, flushing...",
            level="info"
        )
        
        # Flush to ensure events are actually sent before script exits
        # timeout is in seconds - wait up to 10 seconds for events to be sent
        logger.info("Flushing Sentry events (waiting up to 10 seconds)...")
        import time
        start_time = time.time()
        try:
            flush_success = sentry_sdk.flush(timeout=10)
            elapsed = time.time() - start_time
            logger.info(f"Flush completed in {elapsed:.2f} seconds")
            
            if flush_success:
                logger.info("✅ Events successfully sent to Sentry!")
            else:
                logger.warning("⚠️  Flush returned False - events may still be sending in background")
                logger.warning(f"⚠️  Flush completed in {elapsed:.2f}s (timeout was 10s)")
                if elapsed < 1.0:
                    logger.warning("⚠️  Very fast failure suggests events may not be queued properly")
                logger.warning("⚠️  This could mean:")
                logger.warning("    - Network connectivity issues")
                logger.warning("    - Invalid or misconfigured DSN")
                logger.warning("    - Sentry server issues")
                logger.warning("⚠️  Check your Sentry dashboard to confirm events were received")
                logger.warning("⚠️  Events may still be queued and will send when connection is available")
        except Exception as flush_error:
            logger.error(f"❌ Error during flush: {flush_error}")
            logger.error("This suggests a configuration or connection problem")
        
        # Re-raise to see the full traceback in console
        raise

