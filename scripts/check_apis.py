#!/usr/bin/env python3
"""
API Health Check Script
Verifies all service integrations listed in .env
"""
import asyncio
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

from loguru import logger
from src.config import settings
from src.db.base import db
from src.services.ai_provider_health import AIProviderHealthService
from src.services.gemini_client import GeminiClient
from src.services.openrouter_client import OpenRouterClient
from src.services.storage_service import StorageService


async def run_health_checks():
    """Run all API and service health checks"""
    print(f"\n{'='*50}")
    print(f"  {settings.app_name} - API Health Check")
    print(f"{'='*50}\n")

    # Initialize services
    logger.remove()  # Remove default logger to keep output clean
    logger.add(sys.stderr, level="WARNING")

    gemini_client = GeminiClient()
    openrouter_client = OpenRouterClient() if settings.openrouter_api_key else None
    storage_service = StorageService()
    
    # Initialize database
    await db.connect()

    health_service = AIProviderHealthService(
        gemini_client=gemini_client,
        storage_service=storage_service,
        database=db,
        openrouter_client=openrouter_client
    )

    try:
        # Check all services
        results = await health_service.check_all_providers()

        # 1. Configuration Section
        print(f"\n[1] Application Configuration")
        print("-" * 30)
        config = results["config"]
        status_color = "\033[92m" if config.status == "valid" else "\033[91m"
        print(f"Status: {status_color}{config.status.upper()}\033[0m")
        for key, val in config.details.items():
            print(f"  {key:<15}: {val}")
        if config.errors:
            print("\033[91mErrors:\033[0m")
            for err in config.errors:
                print(f"  - {err}")

        # 2. External APIs Section
        print(f"\n[2] External APIs")
        print("-" * 80)
        print(f"{'Service':<20} | {'Status':<12} | {'Latency':<10} | {'Info/Error'}")
        print("-" * 80)

        api_services = ["gemini", "openrouter"]
        for name in api_services:
            health = results[name]
            status_color = "\033[92m" if health.status == "up" else "\033[91m"
            if health.status == "unconfigured":
                status_color = "\033[93m"
            
            reset_color = "\033[0m"
            status_text = f"{status_color}{health.status.upper():<12}{reset_color}"
            latency = f"{health.latency_ms}ms" if health.latency_ms is not None else "N/A"
            error = health.error if health.status == "down" else ""
            print(f"{name.capitalize():<20} | {status_text} | {latency:<10} | {error}")

        # 3. Infrastructure Section
        print(f"\n[3] Infrastructure & Storage")
        print("-" * 80)
        infra_services = ["storage", "database", "litestream", "sentry"]
        for name in infra_services:
            health = results[name]
            status = health.status
            status_color = "\033[92m" if status in ["up", "configured", "enabled"] else "\033[91m"
            if status == "unconfigured":
                status_color = "\033[93m"
            
            reset_color = "\033[0m"
            status_text = f"{status_color}{status.upper():<12}{reset_color}"
            
            info = ""
            if name == "database" and status == "up":
                info = f"Tables: {health.table_count}, Size: {health.size_mb}MB"
            elif name == "storage" and status == "up":
                latency = f"{health.latency_ms}ms"
                info = f"Latency: {latency}"
            elif name == "litestream" and status == "configured":
                info = f"Bucket: {health.details['bucket']}"
            elif name == "sentry" and status == "enabled":
                info = f"Env: {health.details['environment']}"
            elif health.error:
                info = health.error
                
            print(f"{name.capitalize():<20} | {status_text} | {info}")

        print(f"\n{'='*80}\n")

    finally:
        # Cleanup
        await gemini_client.close()
        if openrouter_client:
            await openrouter_client.close()
        await db.disconnect()


if __name__ == "__main__":
    try:
        asyncio.run(run_health_checks())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"\nFatal error: {e}")
        sys.exit(1)
