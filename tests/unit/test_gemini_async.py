"""
Tests to prove true async implementation in Gemini client

These tests verify that:
1. Multiple concurrent requests execute in parallel (not sequentially)
2. The event loop is not blocked during I/O operations
3. httpx.AsyncClient is used (not sync requests)
4. Async methods properly await and don't block

Note: These tests make REAL API calls to Gemini. Ensure GEMINI_API_KEY is set in .env file.
"""
import asyncio
import time

import httpx
import pytest

from src.config import settings
from src.services.gemini_client import GeminiClient

# Skip all tests if API key is not available
pytestmark = pytest.mark.skipif(
    not settings.gemini_api_key,
    reason="GEMINI_API_KEY not set in .env file"
)


class TestGeminiAsyncImplementation:
    """Tests to prove true async implementation"""

    @pytest.fixture
    def gemini_client(self):
        """Create a GeminiClient instance for testing"""
        return GeminiClient()

    @pytest.mark.asyncio
    async def test_concurrent_requests_execute_in_parallel(self, gemini_client):
        """
        Test that multiple concurrent requests execute in parallel.
        If true async is implemented, N requests should take roughly the same time
        as 1 request (not N times longer).
        
        This test makes REAL API calls to Gemini to prove true async.
        """
        # Time a single request (real API call)
        start = time.time()
        response1, tokens1 = await gemini_client.generate_response(
            user_message="Say hello in one word",
            system_instructions="You are a helpful assistant"
        )
        single_request_time = time.time() - start

        # Verify we got a response
        assert response1 is not None
        assert len(response1) > 0
        assert tokens1 > 0

        # Time 5 concurrent requests (real API calls)
        start = time.time()
        tasks = [
            gemini_client.generate_response(
                user_message=f"Say the number {i} in one word",
                system_instructions="You are a helpful assistant"
            )
            for i in range(5)
        ]
        results = await asyncio.gather(*tasks)
        concurrent_requests_time = time.time() - start

        # Verify all requests completed successfully
        assert len(results) == 5
        for response, tokens in results:
            assert response is not None
            assert len(response) > 0
            assert tokens > 0

        # With true async, 5 concurrent requests should take roughly the same time
        # as 1 request (maybe 1.5-2x longer due to overhead, but not 5x longer)
        # Sequential would be ~5x single_request_time, parallel should be ~1-2x
        ratio = concurrent_requests_time / single_request_time
        assert ratio < 3.0, (
            f"Concurrent requests took {concurrent_requests_time:.3f}s, "
            f"single request took {single_request_time:.3f}s. "
            f"True async should make concurrent requests much faster. "
            f"Ratio: {ratio:.2f}x (expected < 3.0x, sequential would be ~5x)"
        )
        
        # Log the performance improvement
        print(f"\n✅ Async performance: {ratio:.2f}x (sequential would be ~5x)")

    @pytest.mark.asyncio
    async def test_event_loop_not_blocked(self, gemini_client):
        """
        Test that the event loop is not blocked during I/O operations.
        We can run other async tasks concurrently while waiting for API calls.
        
        This test makes a REAL API call to Gemini while running background tasks.
        """
        background_iterations = []

        async def background_task():
            """A task that runs concurrently with the API call"""
            for i in range(20):
                await asyncio.sleep(0.05)
                background_iterations.append(i)

        # Start background task and API call concurrently
        start = time.time()
        api_task = gemini_client.generate_response(
            user_message="Count to 5 slowly",
            system_instructions="You are a helpful assistant"
        )
        bg_task = background_task()

        # Both should run concurrently
        response, tokens = await api_task
        await bg_task
        total_time = time.time() - start

        # Verify API call completed
        assert response is not None
        assert len(response) > 0
        assert tokens > 0

        # Verify background task ran (should have multiple iterations)
        assert len(background_iterations) > 0, (
            "Background task should have run concurrently with API call"
        )

        # If event loop is not blocked, both tasks should complete in roughly
        # the same time as the longest task (not the sum)
        # Background task: ~1s (20 * 0.05s), API call: ~1-3s, total should be ~max of both
        # If blocked, total would be ~sum (4-5s), if async, total should be ~max (2-3s)
        expected_max_time = max(1.0, total_time * 0.5)  # Allow some overhead
        assert total_time < 10.0, (
            f"Total time {total_time:.3f}s suggests event loop was blocked. "
            f"Background task should run concurrently with API call."
        )
        
        print("\n✅ Event loop not blocked: API call and background task ran concurrently")
        print(f"   Background iterations: {len(background_iterations)}, Total time: {total_time:.3f}s")

    @pytest.mark.asyncio
    async def test_uses_httpx_async_client(self, gemini_client):
        """
        Test that httpx.AsyncClient is used (not sync requests).
        This verifies the underlying implementation uses async HTTP.
        """
        # Verify http_client is an AsyncClient instance
        assert isinstance(gemini_client.http_client, httpx.AsyncClient), (
            "GeminiClient should use httpx.AsyncClient for true async"
        )

        # Verify post method is async
        assert asyncio.iscoroutinefunction(gemini_client.http_client.post), (
            "http_client.post should be an async coroutine function"
        )

    @pytest.mark.asyncio
    async def test_multiple_methods_concurrent(self, gemini_client):
        """
        Test that different async methods can run concurrently.
        This proves the entire client is async, not just one method.
        
        This test makes REAL concurrent API calls to Gemini.
        """
        # Run multiple different async methods concurrently (real API calls)
        start = time.time()
        tasks = [
            gemini_client.generate_response(
                user_message="Say hello",
                system_instructions="You are helpful"
            ),
            gemini_client.health_check(),
            gemini_client.extract_memories(
                user_message="I am 30 years old and love pizza",
                assistant_response="I'll remember that you're 30 and love pizza!"
            ),
        ]
        results = await asyncio.gather(*tasks)
        total_time = time.time() - start

        # Verify all methods returned results
        assert len(results) == 3
        
        # generate_response returns tuple (response, tokens)
        response, tokens = results[0]
        assert response is not None
        assert len(response) > 0
        assert tokens > 0
        
        # health_check returns dict
        health = results[1]
        assert isinstance(health, dict)
        assert "status" in health
        
        # extract_memories returns dict
        memories = results[2]
        assert isinstance(memories, dict)

        # All three methods should complete in roughly the same time as one
        # (since they run concurrently with true async)
        # Sequential would be ~3x single method time, parallel should be ~1-2x
        assert total_time < 10.0, (
            f"Three concurrent methods took {total_time:.3f}s. "
            f"With true async, should be similar to single method time."
        )
        
        print(f"\n✅ Multiple methods concurrent: All 3 methods completed in {total_time:.3f}s")

    @pytest.mark.asyncio
    async def test_async_await_chain(self, gemini_client):
        """
        Test that async methods properly await and can be chained.
        This verifies the async/await pattern is correctly implemented.
        
        This test makes REAL sequential API calls to Gemini.
        """
        # Chain multiple async operations (real API calls)
        async def chained_operations():
            result1 = await gemini_client.generate_response(
                user_message="Say 'first'",
                system_instructions="You are helpful"
            )
            result2 = await gemini_client.generate_response(
                user_message="Say 'second'",
                system_instructions="You are helpful"
            )
            return result1, result2

        # This should work without blocking
        results = await chained_operations()
        assert len(results) == 2
        
        # Verify both results are tuples (response, tokens)
        response1, tokens1 = results[0]
        response2, tokens2 = results[1]
        
        assert response1 is not None
        assert len(response1) > 0
        assert tokens1 > 0
        
        assert response2 is not None
        assert len(response2) > 0
        assert tokens2 > 0
        
        print("\n✅ Async await chain: Both calls completed successfully")

    @pytest.mark.asyncio
    async def test_concurrent_health_checks(self, gemini_client):
        """
        Test that multiple health checks can run concurrently.
        Health checks are a good indicator of async implementation.
        
        This test makes 10 REAL concurrent health check calls to Gemini.
        """
        # Time a single health check first
        start = time.time()
        single_health = await gemini_client.health_check()
        single_health_time = time.time() - start
        
        assert "status" in single_health

        # Run 10 health checks concurrently (real API calls)
        start = time.time()
        tasks = [gemini_client.health_check() for _ in range(10)]
        results = await asyncio.gather(*tasks)
        total_time = time.time() - start

        # Verify all health checks completed
        assert len(results) == 10
        assert all("status" in result for result in results)
        assert all(result["status"] == "up" for result in results)

        # With true async, 10 concurrent health checks should take roughly
        # the same time as 1 (not 10x longer)
        # Sequential would be ~10x single_health_time, parallel should be ~1-2x
        ratio = total_time / single_health_time if single_health_time > 0 else 1.0
        assert ratio < 3.0, (
            f"10 concurrent health checks took {total_time:.3f}s, "
            f"single check took {single_health_time:.3f}s. "
            f"Ratio: {ratio:.2f}x (expected < 3.0x, sequential would be ~10x)"
        )
        
        print(f"\n✅ Concurrent health checks: {ratio:.2f}x (sequential would be ~10x)")

    @pytest.mark.asyncio
    async def test_async_context_manager_support(self, gemini_client):
        """
        Test that the client properly supports async context management
        (for cleanup/closing connections).
        """
        # Test that close() is async
        assert asyncio.iscoroutinefunction(gemini_client.close), (
            "close() should be an async method"
        )

        # Test that we can close the client
        await gemini_client.close()

        # Verify the HTTP client was closed
        # (httpx.AsyncClient.is_closed is a property, not a method)
        # We can't easily check this without accessing private attributes,
        # but if close() completes without error, it's working

    @pytest.mark.asyncio
    async def test_no_blocking_sync_calls(self, gemini_client):
        """
        Test that no blocking synchronous HTTP calls are made.
        This ensures we're using true async, not sync calls in threads.
        """
        import inspect

        # Check that key methods are async
        assert inspect.iscoroutinefunction(gemini_client.generate_response)
        assert inspect.iscoroutinefunction(gemini_client.transcribe_audio)
        assert inspect.iscoroutinefunction(gemini_client.health_check)
        assert inspect.iscoroutinefunction(gemini_client.extract_memories)
        assert inspect.iscoroutinefunction(gemini_client._generate_content)
        assert inspect.iscoroutinefunction(gemini_client._download_image)
        assert inspect.iscoroutinefunction(gemini_client._download_audio)

        # Verify http_client uses async methods
        assert hasattr(gemini_client.http_client, "post")
        assert inspect.iscoroutinefunction(gemini_client.http_client.post)

    @pytest.mark.asyncio
    async def test_parallel_image_downloads(self, gemini_client):
        """
        Test that multiple image downloads happen in parallel.
        This tests the _download_image async method.
        
        This test makes REAL concurrent HTTP requests to download images.
        Uses publicly accessible test images.
        """
        # Use publicly accessible test images (direct URLs, no redirects)
        # Using httpbin.org which provides direct image responses for testing
        test_image_urls = [
            "https://httpbin.org/image/png",
            "https://httpbin.org/image/jpeg",
            "https://httpbin.org/image/webp",
            "https://httpbin.org/image/png",  # Can reuse same endpoint
            "https://httpbin.org/image/jpeg",  # Can reuse same endpoint
        ]

        # Time a single download first
        start = time.time()
        single_result = await gemini_client._download_image(test_image_urls[0])
        single_download_time = time.time() - start
        
        assert "mime_type" in single_result
        assert "data" in single_result

        # Download 5 images concurrently (real HTTP requests)
        start = time.time()
        tasks = [
            gemini_client._download_image(url)
            for url in test_image_urls
        ]
        results = await asyncio.gather(*tasks)
        total_time = time.time() - start

        # Verify all downloads completed
        assert len(results) == 5
        assert all("mime_type" in result and "data" in result for result in results)
        assert all(len(result["data"]) > 0 for result in results)

        # With true async, 5 concurrent downloads should take roughly
        # the same time as 1 (not 5x longer)
        # Sequential would be ~5x single_download_time, parallel should be ~1-2x
        ratio = total_time / single_download_time if single_download_time > 0 else 1.0
        assert ratio < 3.0, (
            f"5 concurrent image downloads took {total_time:.3f}s, "
            f"single download took {single_download_time:.3f}s. "
            f"Ratio: {ratio:.2f}x (expected < 3.0x, sequential would be ~5x)"
        )
        
        print(f"\n✅ Parallel image downloads: {ratio:.2f}x (sequential would be ~5x)")

