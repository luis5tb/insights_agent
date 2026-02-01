# Rate Limiting

This document describes the simplified rate limiting system for controlling API usage.

## Overview

The rate limiting system enforces global usage limits using an in-memory sliding window algorithm:
- Requests per minute
- Requests per hour

No Redis or external dependencies are required.

## Architecture

```
┌─────────────────┐     ┌───────────────────┐     ┌─────────────────┐
│  API Request    │────▶│RateLimitMiddleware│────▶│SimpleRateLimiter│
│                 │     │                   │     │   (in-memory)   │
└─────────────────┘     └───────────────────┘     └─────────────────┘
```

### Components

| Component | File | Description |
|-----------|------|-------------|
| `RateLimitMiddleware` | `ratelimit/middleware.py` | FastAPI middleware for enforcement |
| `SimpleRateLimiter` | `ratelimit/middleware.py` | In-memory sliding window limiter |

## Configuration

### Environment Variables

```bash
# Global rate limits
RATE_LIMIT_REQUESTS_PER_MINUTE=60
RATE_LIMIT_REQUESTS_PER_HOUR=1000
```

## Rate-Limited Paths

Only specific paths are rate-limited:

| Path | Description |
|------|-------------|
| `/` | A2A JSON-RPC endpoint (supports both send and streaming) |

### Skipped Paths

These paths are never rate-limited:

- `/health`, `/healthz`, `/ready` - Health checks
- `/metrics` - Prometheus metrics
- `/.well-known/agent.json` - Agent card
- `/docs`, `/openapi.json`, `/redoc` - Documentation

## Response Headers

When a request is rate-limited (429 response):

| Header | Description |
|--------|-------------|
| `Retry-After` | Seconds until the limit resets |
| `X-RateLimit-Limit` | The limit per minute |
| `X-RateLimit-Remaining` | Remaining requests |

Example response:
```http
HTTP/1.1 429 Too Many Requests
Retry-After: 60
X-RateLimit-Limit: 60
X-RateLimit-Remaining: 0
Content-Type: application/json

{
  "error": "rate_limit_exceeded",
  "message": "Rate limit exceeded (per_minute)",
  "retry_after": 60
}
```

## How It Works

### Sliding Window Algorithm

The rate limiter uses a simple sliding window algorithm:

1. Each request timestamp is stored in memory
2. Old timestamps (> 1 minute / 1 hour) are pruned
3. Count is compared against configured limits

### Request Flow

```
1. Request arrives
2. Middleware checks if path should be rate-limited
3. SimpleRateLimiter checks current counts against limits
4. If within limits:
   - Record timestamp
   - Allow request
5. If exceeded:
   - Return 429 Too Many Requests
   - Include Retry-After header
```

## Testing Rate Limiting

```bash
# Make 70 requests quickly (default limit is 60/min)
for i in {1..70}; do
  echo -n "Request $i: "
  curl -s -o /dev/null -w "%{http_code}\n" \
    -X POST http://localhost:8000/ \
    -H "Content-Type: application/json" \
    -d '{"jsonrpc":"2.0","method":"message/send","id":'$i',"params":{"message":{"role":"user","parts":[{"type":"text","text":"test"}]}}}'
done
```

You should see 429 responses after 60 requests.

## Rate Limiting vs Usage Tracking

The agent has two separate systems for managing API usage:

| System | Purpose | Mechanism |
|--------|---------|-----------|
| **Rate Limiting** | Prevent abuse | FastAPI middleware, rejects excess requests |
| **Usage Tracking** | Monitor consumption | ADK plugin, counts tokens and tool calls |

Rate limiting happens **before** the request is processed (at the middleware layer), while usage tracking happens **during** request processing (via ADK plugin callbacks).

## Usage Statistics

Token usage and request counts are tracked via the `UsageTrackingPlugin` (using ADK's plugin system). Access aggregate statistics at:

```bash
curl http://localhost:8000/usage
```

Response:
```json
{
  "status": "ok",
  "usage": {
    "total_input_tokens": 1234,
    "total_output_tokens": 5678,
    "total_tokens": 6912,
    "total_requests": 42,
    "total_tool_calls": 15
  }
}
```

See [Usage Tracking and Metering](metering.md) for detailed documentation on the plugin system and how to extend it for production use.

## Limitations

The in-memory rate limiter:
- Resets when the application restarts
- Is per-instance (not shared across replicas)
- Does not persist state

For production deployments with multiple replicas, consider implementing a shared rate limiter using Redis or a similar distributed store.
