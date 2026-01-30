# Rate Limiting

This document describes the rate limiting system for controlling API usage and preventing abuse.

## Overview

The rate limiting system enforces usage limits based on subscription tiers:
- Requests per minute
- Requests per hour
- Tokens per day
- Concurrent requests

## Architecture

```
┌─────────────────┐     ┌───────────────────┐     ┌─────────────────┐
│  API Request    │────▶│RateLimitMiddleware│────▶│   RateLimiter   │
│  (with order_id)│     │                   │     │                 │
└─────────────────┘     └───────────────────┘     └────────┬────────┘
                                                           │
                                                           ▼
                                                  ┌─────────────────┐
                                                  │     Redis       │
                                                  │ (sliding window)│
                                                  └─────────────────┘
```

### Components

| Component | File | Description |
|-----------|------|-------------|
| `RateLimitMiddleware` | `ratelimit/middleware.py` | FastAPI middleware for enforcement |
| `RateLimiter` | `ratelimit/limiter.py` | Redis-based rate limiter |
| `RateLimitService` | `ratelimit/service.py` | High-level service interface |
| Models | `ratelimit/models.py` | Subscription tiers and limits |

## Subscription Tiers

| Tier | Requests/min | Requests/hour | Tokens/day | Concurrent |
|------|--------------|---------------|------------|------------|
| FREE | 10 | 100 | 10,000 | 2 |
| BASIC | 30 | 500 | 50,000 | 5 |
| PROFESSIONAL | 60 | 1,000 | 100,000 | 10 |
| ENTERPRISE | 300 | 10,000 | 1,000,000 | 50 |

### Plan to Tier Mapping

| Tier | Plan Names |
|------|------------|
| FREE | `free`, `trial` |
| BASIC | `basic`, `starter` |
| PROFESSIONAL | `professional`, `pro`, `standard` |
| ENTERPRISE | `enterprise`, `premium`, `unlimited` |

## How It Works

### Sliding Window Algorithm

The rate limiter uses a sliding window algorithm with Redis:

1. Each time window (minute, hour, day) has a counter
2. Counters are stored with TTL matching the window duration
3. Requests increment the counter and check against limits

### Request Flow

```
1. Request arrives
2. Middleware extracts order_id and plan from request
3. RateLimiter checks current counts against tier limits
4. If within limits:
   - Increment counters
   - Allow request
5. If exceeded:
   - Return 429 Too Many Requests
   - Include Retry-After header
```

## Rate-Limited Paths

Only specific paths are rate-limited:

| Path | Description |
|------|-------------|
| `/a2a` | A2A SendMessage endpoint |
| `/a2a/stream` | A2A streaming endpoint |
| `/oauth/token` | Token endpoint |
| `/oauth/userinfo` | User info endpoint |

### Skipped Paths

These paths are never rate-limited:

- `/health`, `/healthz`, `/ready` - Health checks
- `/metrics` - Prometheus metrics
- `/.well-known/agent.json` - Agent card
- `/docs`, `/openapi.json`, `/redoc` - Documentation
- `/oauth/authorize`, `/oauth/callback`, `/auth/callback` - OAuth flow

## Response Headers

When a request is rate-limited (429 response):

| Header | Description |
|--------|-------------|
| `Retry-After` | Seconds until the limit resets |
| `X-RateLimit-Limit` | The limit that was exceeded |
| `X-RateLimit-Remaining` | Remaining requests (0) |
| `X-RateLimit-Reset` | Seconds until reset |

Example response:
```http
HTTP/1.1 429 Too Many Requests
Retry-After: 45
X-RateLimit-Limit: 10
X-RateLimit-Remaining: 0
X-RateLimit-Reset: 45
Content-Type: application/json

{
  "error": "rate_limit_exceeded",
  "message": "Rate limit exceeded: minute",
  "retry_after": 45
}
```

## Configuration

### Environment Variables

```bash
# Redis connection (required for rate limiting)
REDIS_URL=redis://localhost:6379/0

# Default rate limits (optional, uses tier defaults)
RATE_LIMIT_REQUESTS_PER_MINUTE=60
RATE_LIMIT_REQUESTS_PER_HOUR=1000
RATE_LIMIT_TOKENS_PER_DAY=100000
```

### Redis Requirement

Rate limiting requires Redis. Without Redis:
- Rate limiter will log warnings
- Requests will be allowed (fail-open)

## Requirements for Rate Limiting

For rate limiting to work, you need **all** of the following:

| Requirement | Why |
|-------------|-----|
| **Redis running** | Stores rate limit counters with sliding window algorithm |
| **`X-Order-ID` header** | Identifies which customer/subscription to rate limit |
| **`Authorization` header** | Required for authenticated endpoints (use any value with `SKIP_JWT_VALIDATION=true`) |

**Important:** If any requirement is missing, requests are **allowed through** (fail-open behavior):
- No Redis → Warning logged, request allowed
- No `X-Order-ID` → Request allowed without tracking
- Redis error → Warning logged, request allowed

## Local Testing

### Option 1: Using Podman Pod (Recommended)

The Podman pod includes Redis, so rate limiting works out of the box.

1. Start the pod:
```bash
make run
# Or manually:
podman kube play deploy/podman/insights-agent-pod.yaml
```

2. Test rate limiting (FREE tier = 10 req/min):
```bash
# Make 15 requests - should see 429 after request 10
for i in {1..15}; do
  echo -n "Request $i: "
  curl -s -o /dev/null -w "%{http_code}\n" \
    -X POST http://localhost:8000/a2a \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer dummy-token" \
    -H "X-Order-ID: test-order" \
    -d '{"jsonrpc":"2.0","method":"message/send","id":'$i',"params":{"message":{"messageId":"msg-'$i'","role":"user","parts":[{"type":"text","text":"test"}]}}}'
done
```

3. Check rate limit response details:
```bash
# See full response when rate limited
curl -i -X POST http://localhost:8000/a2a \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer dummy-token" \
  -H "X-Order-ID: test-order" \
  -d '{"jsonrpc":"2.0","method":"message/send","id":1,"params":{"message":{"messageId":"msg-1","role":"user","parts":[{"type":"text","text":"test"}]}}}'
```

4. Reset rate limits between tests:
```bash
# Connect to Redis in the pod
podman exec -it insights-agent-pod-redis redis-cli FLUSHDB
```

### Option 2: Development Mode (Without Podman)

1. Start Redis:
```bash
# Using Docker
docker run -d --name redis -p 6379:6379 redis:alpine

# Or using Podman
podman run -d --name redis -p 6379:6379 redis:alpine
```

2. Configure environment:
```bash
# .env
REDIS_URL=redis://localhost:6379/0
SKIP_JWT_VALIDATION=true
```

3. Start the server:
```bash
source .venv/bin/activate
python -m insights_agent.main
```

4. Test rate limiting:
```bash
# Make 15 requests - should see 429 after request 10
for i in {1..15}; do
  echo -n "Request $i: "
  curl -s -o /dev/null -w "%{http_code}\n" \
    -X POST http://localhost:8000/a2a \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer dummy-token" \
    -H "X-Order-ID: test-order" \
    -d '{"jsonrpc":"2.0","method":"message/send","id":'$i',"params":{"message":{"messageId":"msg-'$i'","role":"user","parts":[{"type":"text","text":"test"}]}}}'
done
```

With FREE tier (10 req/min), you should see 429 after 10 requests.

### Option 3: Without Redis (No Rate Limiting)

If Redis is not running, rate limiting is disabled:

```bash
# Start server (rate limiting will be skipped)
python -m insights_agent.main

# All requests allowed - no 429 responses
curl -X POST http://localhost:8000/a2a \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer dummy-token" \
  -H "X-Order-ID: test-order" \
  -d '{"jsonrpc":"2.0","method":"message/send","id":1,"params":{"message":{"role":"user","parts":[{"type":"text","text":"test"}]}}}'
```

### Option 4: Using Python

```python
import asyncio
from insights_agent.ratelimit.limiter import get_rate_limiter
from insights_agent.ratelimit.models import SubscriptionTier

async def test_rate_limiting():
    limiter = get_rate_limiter()
    order_id = "test-order"
    plan = "free"  # Maps to FREE tier

    print(f"Testing with plan: {plan}")
    tier = SubscriptionTier.from_plan(plan)
    print(f"Tier: {tier.name}")
    print(f"Limits: {tier.requests_per_minute}/min, {tier.requests_per_hour}/hr")

    # Check current status
    status = await limiter.check_rate_limit(order_id, plan)
    print(f"\nCurrent status:")
    print(f"  Requests this minute: {status.requests_this_minute}")
    print(f"  Requests this hour: {status.requests_this_hour}")
    print(f"  Is rate limited: {status.is_rate_limited}")

    # Simulate requests
    print(f"\nSimulating 12 requests...")
    for i in range(12):
        status = await limiter.check_rate_limit(order_id, plan)
        if status.is_rate_limited:
            print(f"  Request {i+1}: BLOCKED (retry after {status.retry_after_seconds}s)")
        else:
            await limiter.increment_request_count(order_id)
            print(f"  Request {i+1}: OK")

    # Final status
    status = await limiter.check_rate_limit(order_id, plan)
    print(f"\nFinal status:")
    print(f"  Requests this minute: {status.requests_this_minute}")
    print(f"  Is rate limited: {status.is_rate_limited}")

    # Cleanup
    await limiter.close()

asyncio.run(test_rate_limiting())
```

### Option 5: Test Different Tiers

```bash
.venv/bin/python << 'EOF'
from insights_agent.ratelimit.models import SubscriptionTier

print("Subscription Tiers:\n")
for tier in SubscriptionTier:
    print(f"{tier.name}:")
    print(f"  Requests per minute: {tier.requests_per_minute}")
    print(f"  Requests per hour: {tier.requests_per_hour}")
    print(f"  Tokens per day: {tier.tokens_per_day:,}")
    print(f"  Concurrent requests: {tier.concurrent_requests}")
    print()

print("Plan mappings:")
for plan in ["free", "trial", "basic", "starter", "professional", "pro", "enterprise", "premium"]:
    tier = SubscriptionTier.from_plan(plan)
    print(f"  {plan} -> {tier.name}")
EOF
```

## Checking Rate Limit Status

### Via RateLimitService

```python
from insights_agent.ratelimit.service import RateLimitService

service = RateLimitService()

# Check status
status = await service.get_status(order_id="order-123", plan="basic")
print(f"Rate limited: {status.is_rate_limited}")
print(f"Limit type: {status.limit_type}")  # "minute", "hour", "tokens", "concurrent"

# Check remaining tokens
remaining = await service.get_remaining_tokens(order_id="order-123", plan="basic")
print(f"Remaining tokens today: {remaining}")
```

### Via Redis Directly

```bash
# Connect to Redis
redis-cli

# View rate limit keys
KEYS ratelimit:*

# Check minute counter
GET ratelimit:minute:order-123:12345

# Check hour counter
GET ratelimit:hour:order-123:12345

# Check daily token usage
GET ratelimit:tokens:order-123:20240130
```

## Token-Based Rate Limiting

In addition to request-based limits, there's a daily token limit:

```python
# Track token usage after LLM response
await limiter.add_token_usage(order_id, token_count=1500)

# Check if token limited
is_limited = await service.is_token_limited(order_id, plan)
```

The `TokenUsageMiddleware` automatically tracks tokens from `request.state.token_usage`.

## Concurrent Request Limiting

To prevent resource exhaustion:

```python
# Start request
await limiter.increment_concurrent(order_id)

try:
    # Process request...
    pass
finally:
    # End request
    await limiter.decrement_concurrent(order_id)
```

## Admin Operations

### Reset Limits

For testing or customer support:

```python
# Reset all limits for an order
await limiter.reset_limits(order_id)
```

### View All Orders' Usage

```bash
redis-cli KEYS "ratelimit:*" | sort
```

## Troubleshooting

### Rate limiting not working

**Step 1: Check Redis is running**
```bash
# For standalone Redis
redis-cli ping
# Should return: PONG

# For Podman pod
podman exec -it insights-agent-pod-redis redis-cli ping
```

**Step 2: Verify REDIS_URL**
```bash
echo $REDIS_URL
# Should be: redis://localhost:6379/0
```

**Step 3: Check logs for errors**
```bash
# Look for "Rate limiting error" messages
make logs | grep -i "rate"
```

### Requests not being rate-limited

**Common causes:**

| Symptom | Cause | Solution |
|---------|-------|----------|
| All requests return 200 | Missing `X-Order-ID` header | Add `-H "X-Order-ID: test-order"` |
| All requests return 200 | Redis not running | Start Redis or use Podman pod |
| All requests return 200 | Redis connection error | Check `REDIS_URL` and connectivity |
| All requests return 401 | Missing `Authorization` header | Add `-H "Authorization: Bearer dummy-token"` |

**Verify your request has all required headers:**
```bash
curl -v -X POST http://localhost:8000/a2a \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer dummy-token" \
  -H "X-Order-ID: test-order" \
  -d '{"jsonrpc":"2.0","method":"message/send","id":1,"params":{"message":{"role":"user","parts":[{"type":"text","text":"test"}]}}}'
```

**Check if rate limit keys are being created in Redis:**
```bash
# For Podman pod
podman exec -it insights-agent-pod-redis redis-cli KEYS "ratelimit:*"

# For standalone Redis
redis-cli KEYS "ratelimit:*"
```

If no keys appear, the `X-Order-ID` header is likely missing.

### 429 errors in development

1. Reset limits:
```python
await limiter.reset_limits("your-order-id")
```

2. Or flush Redis:
```bash
redis-cli FLUSHDB
```

3. Or use a higher tier for testing:
```bash
# Set plan in request state or use X-Plan header
```

### Redis connection issues

```bash
# Check Redis is running
docker ps | grep redis

# Check connectivity
redis-cli -u $REDIS_URL ping

# Check memory usage
redis-cli INFO memory
```

## Production Considerations

### Redis High Availability

For production, use Redis Cluster or Redis Sentinel:

```bash
REDIS_URL=redis://redis-sentinel:26379/0?sentinel=mymaster
```

### Fail-Open vs Fail-Closed

Current implementation fails open (allows requests if Redis is unavailable). For stricter control:

```python
# In limiter.py, change error handling to fail closed
if redis_error:
    raise RateLimitError("Rate limiting unavailable")
```

### Monitoring

Monitor these metrics:
- Rate limit hits per tier
- Redis latency
- Token usage trends

```python
# The metering system tracks rate-limited requests
await metering.track_rate_limited(order_id, client_id)
```
