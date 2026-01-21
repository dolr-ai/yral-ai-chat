#!/usr/bin/env python3
"""
Fuzz/stress test for chat API endpoints to identify performance bottlenecks.
Tests concurrent requests to send_message and create_conversation.
"""
import asyncio
import json
import statistics
import time
from datetime import datetime, timedelta

import httpx
import jwt

BASE_URL = "http://localhost:8000"
JWT_SECRET = None  # Will be loaded from .env


def load_jwt_secret():
    """Load JWT secret from .env file"""
    global JWT_SECRET
    try:
        with open(".env") as f:
            for line in f:
                if line.startswith("JWT_SECRET_KEY="):
                    JWT_SECRET = line.split("=", 1)[1].strip().strip('"\'')
                    break
    except FileNotFoundError:
        pass

    if not JWT_SECRET:
        raise ValueError("JWT_SECRET_KEY not found in .env file")


def generate_test_token(user_id: str) -> str:
    """Generate a valid JWT token for testing"""
    from datetime import UTC
    payload = {
        "sub": user_id,
        "user_id": user_id,
        "iss": "https://auth.yral.com",
        "exp": datetime.now(UTC) + timedelta(hours=1),
        "iat": datetime.now(UTC),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


async def get_influencer_id(client: httpx.AsyncClient) -> str:
    """Get first available influencer ID"""
    resp = await client.get(f"{BASE_URL}/api/v1/influencers")
    data = resp.json()
    return data["influencers"][0]["id"]


async def create_conversation(
    client: httpx.AsyncClient,
    token: str,
    influencer_id: str
) -> tuple[str | None, float, str | None]:
    """Create conversation and return (conversation_id, duration_ms, error)"""
    start = time.time()
    try:
        resp = await client.post(
            f"{BASE_URL}/api/v1/chat/conversations",
            json={"influencer_id": influencer_id},
            headers={"Authorization": f"Bearer {token}"},
            timeout=120.0
        )
        duration_ms = (time.time() - start) * 1000

        if resp.status_code in (200, 201):
            return resp.json()["id"], duration_ms, None
        else:
            return None, duration_ms, f"HTTP {resp.status_code}: {resp.text[:100]}"
    except Exception as e:
        duration_ms = (time.time() - start) * 1000
        return None, duration_ms, str(e)


async def send_message(
    client: httpx.AsyncClient,
    token: str,
    conversation_id: str,
    message: str
) -> tuple[float, str | None]:
    """Send message and return (duration_ms, error)"""
    start = time.time()
    try:
        resp = await client.post(
            f"{BASE_URL}/api/v1/chat/conversations/{conversation_id}/messages",
            json={"content": message, "message_type": "text"},
            headers={"Authorization": f"Bearer {token}"},
            timeout=120.0
        )
        duration_ms = (time.time() - start) * 1000

        if resp.status_code in (200, 201, 503):  # 503 is fallback error
            return duration_ms, None
        else:
            return duration_ms, f"HTTP {resp.status_code}: {resp.text[:100]}"
    except Exception as e:
        duration_ms = (time.time() - start) * 1000
        return duration_ms, str(e)


def print_stats(name: str, times: list[float], errors: list[str]):
    """Print statistics for a test run"""
    print(f"\n{'='*60}")
    print(f"  {name}")
    print(f"{'='*60}")

    if not times:
        print("  No successful requests")
        return

    times_sorted = sorted(times)
    print(f"  Requests:    {len(times)} successful, {len(errors)} failed")
    print(f"  Min:         {min(times):.0f}ms")
    print(f"  Max:         {max(times):.0f}ms")
    print(f"  Mean:        {statistics.mean(times):.0f}ms")
    print(f"  Median:      {statistics.median(times):.0f}ms")
    print(f"  Std Dev:     {statistics.stdev(times):.0f}ms" if len(times) > 1 else "")
    print(f"  P90:         {times_sorted[int(len(times)*0.9)]:.0f}ms")
    print(f"  P99:         {times_sorted[int(len(times)*0.99)]:.0f}ms")

    slow_count = sum(1 for t in times if t > 5000)
    very_slow_count = sum(1 for t in times if t > 30000)
    print(f"  >5s:         {slow_count} requests")
    print(f"  >30s:        {very_slow_count} requests")

    if errors:
        print(f"\n  Errors ({len(errors)}):")
        for e in errors[:5]:
            print(f"    - {e[:80]}")
        if len(errors) > 5:
            print(f"    ... and {len(errors) - 5} more")


async def test_create_conversation_concurrent(
    num_requests: int = 20,
    concurrency: int = 10
):
    """Test create_conversation with concurrent requests"""
    print(f"\n[TEST] Create Conversation - {num_requests} requests, {concurrency} concurrent")

    load_jwt_secret()
    times = []
    errors = []

    async with httpx.AsyncClient() as client:
        influencer_id = await get_influencer_id(client)

        semaphore = asyncio.Semaphore(concurrency)

        async def bounded_request(i: int):
            async with semaphore:
                user_id = f"fuzz_user_{i}_{int(time.time())}"
                token = generate_test_token(user_id)
                conv_id, duration, error = await create_conversation(
                    client, token, influencer_id
                )
                return duration, error

        start = time.time()
        results = await asyncio.gather(*[bounded_request(i) for i in range(num_requests)])
        total_time = time.time() - start

        for duration, error in results:
            times.append(duration)
            if error:
                errors.append(error)

    print_stats(f"Create Conversation ({concurrency} concurrent)", times, errors)
    print(f"  Total time:  {total_time:.1f}s")
    print(f"  Throughput:  {num_requests/total_time:.1f} req/s")


async def test_send_message_concurrent(
    num_requests: int = 20,
    concurrency: int = 5
):
    """Test send_message with concurrent requests"""
    print(f"\n[TEST] Send Message - {num_requests} requests, {concurrency} concurrent")

    load_jwt_secret()
    times = []
    errors = []

    async with httpx.AsyncClient() as client:
        influencer_id = await get_influencer_id(client)

        # Create conversations first (one per concurrent slot to avoid conflicts)
        conversations = []
        for i in range(concurrency):
            user_id = f"fuzz_msg_user_{i}_{int(time.time())}"
            token = generate_test_token(user_id)
            conv_id, _, error = await create_conversation(client, token, influencer_id)
            if conv_id:
                conversations.append((conv_id, token))
            else:
                print(f"  Failed to create conversation: {error}")

        if not conversations:
            print("  No conversations created, aborting test")
            return

        semaphore = asyncio.Semaphore(concurrency)

        async def bounded_request(i: int):
            async with semaphore:
                conv_id, token = conversations[i % len(conversations)]
                message = f"Test message {i}: Hello, how are you today?"
                duration, error = await send_message(client, token, conv_id, message)
                print(f"  Request {i+1}/{num_requests}: {duration:.0f}ms {'ERROR: ' + error if error else 'OK'}")
                return duration, error

        start = time.time()
        results = await asyncio.gather(*[bounded_request(i) for i in range(num_requests)])
        total_time = time.time() - start

        for duration, error in results:
            times.append(duration)
            if error:
                errors.append(error)

    print_stats(f"Send Message ({concurrency} concurrent)", times, errors)
    print(f"  Total time:  {total_time:.1f}s")
    print(f"  Throughput:  {num_requests/total_time:.2f} req/s")


async def test_mixed_load(duration_seconds: int = 30):
    """Simulate realistic mixed load for a duration"""
    print(f"\n[TEST] Mixed Load - {duration_seconds}s duration")

    load_jwt_secret()

    create_times = []
    send_times = []
    create_errors = []
    send_errors = []

    async with httpx.AsyncClient() as client:
        influencer_id = await get_influencer_id(client)

        # Shared state
        conversations = []
        lock = asyncio.Lock()

        async def create_worker():
            while time.time() < end_time:
                user_id = f"mixed_user_{int(time.time()*1000)}"
                token = generate_test_token(user_id)
                conv_id, duration, error = await create_conversation(
                    client, token, influencer_id
                )
                create_times.append(duration)
                if error:
                    create_errors.append(error)
                elif conv_id:
                    async with lock:
                        conversations.append((conv_id, token))
                await asyncio.sleep(0.5)  # Rate limit

        async def send_worker():
            await asyncio.sleep(2)  # Wait for some conversations to be created
            msg_count = 0
            while time.time() < end_time:
                async with lock:
                    if not conversations:
                        await asyncio.sleep(0.1)
                        continue
                    conv_id, token = conversations[msg_count % len(conversations)]

                message = f"Mixed test message {msg_count}"
                duration, error = await send_message(client, token, conv_id, message)
                send_times.append(duration)
                if error:
                    send_errors.append(error)
                else:
                    print(f"  Message {msg_count+1}: {duration:.0f}ms")
                msg_count += 1
                await asyncio.sleep(0.2)  # Rate limit

        end_time = time.time() + duration_seconds

        # Run 2 create workers and 3 send workers
        await asyncio.gather(
            create_worker(),
            create_worker(),
            send_worker(),
            send_worker(),
            send_worker(),
        )

    print_stats("Create Conversation (mixed)", create_times, create_errors)
    print_stats("Send Message (mixed)", send_times, send_errors)


async def main():
    print("=" * 60)
    print("  FUZZ TEST - Chat API Performance")
    print("=" * 60)
    print(f"  Base URL: {BASE_URL}")
    print(f"  Time: {datetime.now().isoformat()}")

    # Quick health check
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(f"{BASE_URL}/health", timeout=5.0)
            if resp.status_code != 200:
                print(f"\n  ERROR: Server not healthy: {resp.status_code}")
                return
            print("  Server: healthy")
        except Exception as e:
            print(f"\n  ERROR: Cannot connect to server: {e}")
            return

    # Run tests
    await test_create_conversation_concurrent(num_requests=10, concurrency=5)
    await test_send_message_concurrent(num_requests=10, concurrency=3)
    await test_mixed_load(duration_seconds=30)

    print("\n" + "=" * 60)
    print("  FUZZ TEST COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
