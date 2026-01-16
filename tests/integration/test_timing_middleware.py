
import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app


@pytest.mark.asyncio
async def test_timing_middleware_header():
    """Verify that X-Response-Time-Ms header is present in responses"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/")
        assert response.status_code == 200
        assert "X-Response-Time-Ms" in response.headers
        # Verify it's a valid float
        latency = float(response.headers["X-Response-Time-Ms"])
        assert latency >= 0
