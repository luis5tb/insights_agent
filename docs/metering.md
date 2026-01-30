# Metering

This document describes the metering system for tracking API usage and billing metrics.

## Overview

The metering system tracks usage metrics per order (subscription) for:
- API calls (regular and streaming)
- Token usage (input and output)
- MCP tool invocations
- Errors and rate limiting events

## Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  API Request    │────▶│ MeteringMiddleware│────▶│ MeteringService │
│  (with order_id)│     │                  │     │                 │
└─────────────────┘     └──────────────────┘     └────────┬────────┘
                                                          │
                                                          ▼
                                                 ┌─────────────────┐
                                                 │ UsageRepository │
                                                 │  (in-memory)    │
                                                 └─────────────────┘
```

### Components

| Component | File | Description |
|-----------|------|-------------|
| `MeteringMiddleware` | `metering/middleware.py` | Automatically tracks API calls |
| `MeteringService` | `metering/service.py` | Core service for tracking and querying usage |
| `UsageRepository` | `metering/repository.py` | In-memory storage (use database in production) |
| Metering Router | `metering/router.py` | REST API endpoints for querying usage |
| A2A Router | `api/a2a/router.py` | Tracks token usage and MCP tool calls |

### How Metrics Are Captured

| Metric Type | Captured By | Source |
|-------------|-------------|--------|
| API calls | `MeteringMiddleware` | HTTP request count to `/a2a` endpoints |
| Token usage | `A2A Router` | ADK event `usage_metadata` (input/output tokens) |
| MCP tool calls | `A2A Router` | ADK event `get_function_calls()` |
| Errors | `MeteringMiddleware` | HTTP 4xx/5xx responses |

## Metrics Tracked

### Billable Metrics

| Metric | Description |
|--------|-------------|
| `api_calls` | Total API calls |
| `send_message_requests` | Non-streaming A2A SendMessage calls |
| `streaming_requests` | Streaming A2A calls |
| `input_tokens` | LLM input tokens |
| `output_tokens` | LLM output tokens |
| `total_tokens` | Combined token count |
| `mcp_tool_calls` | Total MCP tool invocations |

### Per-Tool Metrics

| Metric | Description |
|--------|-------------|
| `advisor_queries` | Advisor/recommendations tool calls |
| `inventory_queries` | Inventory/hosts tool calls |
| `vulnerability_queries` | Vulnerability/CVE tool calls |
| `remediation_requests` | Remediation tool calls |
| `planning_queries` | Planning tool calls |
| `image_builder_requests` | Image Builder tool calls |

### Non-Billable Metrics

| Metric | Description |
|--------|-------------|
| `errors` | Error count |
| `rate_limited_requests` | Rate-limited request count |
| `tasks_created` | Tasks created |
| `tasks_completed` | Tasks completed |

## API Endpoints

### User Endpoints

Require `metering:read` scope in JWT token.

#### GET /metering/usage

Get usage summary for the authenticated order.

```bash
curl http://localhost:8000/metering/usage \
  -H "Authorization: Bearer $TOKEN"
```

Query parameters:
- `start` (optional): Start of period (default: last hour)
- `end` (optional): End of period (default: now)

Response:
```json
{
  "order_id": "order-123",
  "period_start": "2024-01-30T10:00:00",
  "period_end": "2024-01-30T11:00:00",
  "metrics": {
    "api_calls": 10,
    "input_tokens": 500,
    "output_tokens": 1500
  },
  "total_api_calls": 10,
  "total_tokens": 2000,
  "total_mcp_calls": 5
}
```

#### GET /metering/usage/current

Get current (all-time) usage counters.

```bash
curl http://localhost:8000/metering/usage/current \
  -H "Authorization: Bearer $TOKEN"
```

#### GET /metering/usage/billable

Get billable usage for a specific period.

```bash
curl "http://localhost:8000/metering/usage/billable?start=2024-01-01T00:00:00&end=2024-01-31T23:59:59" \
  -H "Authorization: Bearer $TOKEN"
```

### Admin Endpoints

Require `metering:admin` scope in JWT token.

#### GET /metering/admin/usage/{order_id}

Get usage for any order.

```bash
curl http://localhost:8000/metering/admin/usage/order-123 \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

#### GET /metering/admin/billable

Get billable usage for all orders.

```bash
curl "http://localhost:8000/metering/admin/billable?start=2024-01-01T00:00:00&end=2024-01-31T23:59:59" \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

## What is Order ID?

The `order_id` is a unique identifier that represents a customer's subscription or billing account. It is the primary key used to:

- **Attribute usage** to a specific customer for billing
- **Enforce rate limits** based on subscription tier
- **Report usage** to Google Cloud Marketplace for invoicing

### Where Order ID Comes From

In a production Google Cloud Marketplace integration:

1. **Customer subscribes** via Google Cloud Marketplace
2. **Marketplace creates an entitlement** with an `order_id` (also called `entitlement_id`)
3. **Customer registers via DCR** (Dynamic Client Registration)
4. **JWT tokens** issued to the customer contain the `order_id` in claims

### How Order ID is Extracted

The agent extracts `order_id` from requests in this order of precedence:

1. **JWT token metadata**: The `order_id` claim in the validated token
2. **Fallback to org_id**: If no `order_id` claim, uses the `org_id` claim
3. **X-Order-ID header**: For internal/trusted service-to-service calls

### Testing Without Marketplace

For local development and testing, you can:

1. Set `SKIP_JWT_VALIDATION=true` to disable JWT validation
2. Pass `X-Order-ID: your-test-order` header with each request
3. The metering system will track usage under that order ID

## Local Testing

### Option 1: Using Python Directly

```python
import asyncio
from datetime import datetime, timedelta
from insights_agent.metering.service import get_metering_service

async def test_metering():
    metering = get_metering_service()
    order_id = "test-order-123"

    # Track usage
    await metering.track_api_call(
        order_id=order_id,
        client_id="test-client",
        streaming=False,
    )

    await metering.track_token_usage(
        order_id=order_id,
        input_tokens=100,
        output_tokens=500,
    )

    await metering.track_mcp_call(
        order_id=order_id,
        tool_name="insights_advisor_list_recommendations",
    )

    # Query usage
    current = await metering.get_current_usage(order_id)
    print("Current usage:", current)

    now = datetime.utcnow()
    summary = await metering.get_usage_summary(
        order_id,
        now - timedelta(hours=1),
        now
    )
    print(f"API calls: {summary.total_api_calls}")
    print(f"Tokens: {summary.total_tokens}")
    print(f"MCP calls: {summary.total_mcp_calls}")

asyncio.run(test_metering())
```

### Option 2: Using HTTP with Dev Mode

1. Set environment variables:
```bash
# .env
SKIP_JWT_VALIDATION=true
```

2. Start the server:
```bash
.venv/bin/uvicorn insights_agent.api.app:create_app --factory --reload
```

3. Make an A2A call with order tracking:
```bash
curl -X POST http://localhost:8000/a2a \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer dummy-token" \
  -H "X-Order-ID: my-test-order" \
  -d '{
    "jsonrpc": "2.0",
    "method": "message/send",
    "id": 1,
    "params": {
      "message": {
        "messageId": "msg-1",
        "role": "user",
        "parts": [{"type": "text", "text": "Hello"}]
      }
    }
  }'
```

4. Check metering (dev user has metering scopes):
```bash
# User's own usage (dev-order)
curl http://localhost:8000/metering/usage \
  -H "Authorization: Bearer any-token"

# Admin: check specific order
curl http://localhost:8000/metering/admin/usage/my-test-order \
  -H "Authorization: Bearer any-token"
```

### Option 3: Complete Test Script

```bash
.venv/bin/python << 'EOF'
import asyncio
from datetime import datetime, timedelta
from insights_agent.metering.service import get_metering_service

async def demo():
    metering = get_metering_service()
    order_id = "demo-order"

    print("=== Before ===")
    print(await metering.get_current_usage(order_id))

    # Simulate usage
    for i in range(3):
        await metering.track_api_call(order_id=order_id, streaming=False)
    await metering.track_token_usage(order_id=order_id, input_tokens=150, output_tokens=600)
    await metering.track_mcp_call(order_id=order_id, tool_name="insights_advisor_list_recommendations")

    print("\n=== After ===")
    current = await metering.get_current_usage(order_id)
    for k, v in sorted(current.items()):
        if v > 0:
            print(f"  {k}: {v}")

asyncio.run(demo())
EOF
```

## Production Considerations

### Database Storage

The default `UsageRepository` uses in-memory storage. For production:

1. Implement a database-backed repository (PostgreSQL, BigQuery)
2. Ensure atomic counter increments
3. Implement data retention policies

### Google Cloud Service Control

For Google Cloud Marketplace integration, usage is reported to Service Control:

```python
from insights_agent.service_control import UsageReporter

reporter = UsageReporter()
await reporter.report_usage(order_id, metrics)
```

### Configuration

```bash
# Enable Service Control reporting
SERVICE_CONTROL_ENABLED=true
SERVICE_CONTROL_SERVICE_NAME=your-service.endpoints.your-project.cloud.goog

# Reporting interval (seconds)
USAGE_REPORT_INTERVAL_SECONDS=3600
```

## Troubleshooting

### No usage being tracked

1. Ensure requests have an `order_id` (via auth or X-Order-ID header)
2. Check that requests are going to tracked paths (`/a2a`, `/a2a/stream`)
3. Verify MeteringMiddleware is enabled

### Can't access metering endpoints

1. Ensure JWT token has `metering:read` scope
2. For admin endpoints, need `metering:admin` scope
3. In dev mode (`SKIP_JWT_VALIDATION=true`), any Bearer token works

### Usage not matching expectations

1. Check if requests were rate-limited (not billed)
2. Verify the correct `order_id` is being used
3. Check time range in queries
