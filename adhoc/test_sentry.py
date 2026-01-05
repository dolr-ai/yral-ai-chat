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
from sentry_sdk.integrations.fastapi import FastApiIntegration

from src.config import settings


def init_sentry():
    """Initialize Sentry SDK"""
    if not settings.sentry_dsn:
        logger.warning("SENTRY_DSN not set - Sentry will not be initialized")
        return False

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.environment or "development",
        traces_sample_rate=settings.sentry_traces_sample_rate,
        profiles_sample_rate=settings.sentry_profiles_sample_rate,
        release=settings.sentry_release,
        send_default_pii=True,
        integrations=[FastApiIntegration(transaction_style="endpoint")],
    )
    logger.info(f"Sentry initialized for environment: {settings.environment}")
    return True


def trigger_division_by_zero():
    """Trigger a division by zero error to test Sentry"""
    logger.info("About to trigger division by zero error...")
    
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
    result = numerator / denominator  # This will raise ZeroDivisionError
    return result


if __name__ == "__main__":
    logger.info("Starting Sentry test script...")
    logger.info(f"Environment: {settings.environment}")
    logger.info(f"Sentry DSN configured: {bool(settings.sentry_dsn)}")
    
    # Initialize Sentry
    sentry_initialized = init_sentry()
    
    if not sentry_initialized:
        logger.error("Sentry not initialized - please set SENTRY_DSN in your .env file")
        sys.exit(1)
    
    try:
        trigger_division_by_zero()
    except ZeroDivisionError as e:
        logger.error(f"Division by zero error caught: {e}")
        # The error should be automatically captured by Sentry
        # But we can also manually capture it
        sentry_sdk.capture_exception(e)
        logger.info("Error sent to Sentry!")
        # Re-raise to see the full traceback in console
        raise

