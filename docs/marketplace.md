# Google Cloud Marketplace Integration

This document describes the integration with Google Cloud Marketplace for commercial distribution of the Insights Agent.

## Overview

The Insights Agent integrates with Google Cloud Marketplace to enable:

- **Discovery**: Customers find the agent in the Marketplace catalog
- **Procurement**: Subscription management through Google billing
- **Authentication**: Dynamic Client Registration (DCR) for new subscribers
- **Usage Metering**: Automatic usage tracking and billing
- **Throttling**: Subscription-tier-based rate limiting

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          Google Cloud Marketplace                            │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────────────┐  │
│  │   Catalog &     │  │   Billing &     │  │   Pub/Sub Procurement       │  │
│  │   Discovery     │  │   Subscription  │  │   Notifications             │  │
│  └────────┬────────┘  └────────┬────────┘  └──────────────┬──────────────┘  │
└───────────┼────────────────────┼───────────────────────────┼────────────────┘
            │                    │                           │
            ▼                    ▼                           ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           Insights Agent                                     │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────────────┐  │
│  │   DCR Endpoint  │  │  Usage Metering │  │   Procurement Handler       │  │
│  │   /register     │  │   & Reporting   │  │   (Pub/Sub Subscriber)      │  │
│  └─────────────────┘  └─────────────────┘  └─────────────────────────────┘  │
│                              │                                               │
│                              ▼                                               │
│                    ┌─────────────────┐                                       │
│                    │  Service Control│                                       │
│                    │  API Reporter   │                                       │
│                    └─────────────────┘                                       │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Dynamic Client Registration (DCR)

DCR allows Marketplace customers to automatically register as OAuth clients.

### Flow

```
1. Customer subscribes via Marketplace
2. Marketplace sends procurement notification (Pub/Sub)
3. Customer's application calls POST /oauth/register
4. Agent validates request and creates client credentials
5. Customer uses credentials to authenticate
```

### DCR Endpoint

**POST /oauth/register**

Register a new OAuth client.

**Request:**

```json
{
  "client_name": "Customer Application",
  "redirect_uris": [
    "https://customer-app.example.com/callback"
  ],
  "grant_types": ["authorization_code", "refresh_token"],
  "response_types": ["code"],
  "token_endpoint_auth_method": "client_secret_basic",
  "contacts": ["admin@customer.example.com"]
}
```

**Response:**

```json
{
  "client_id": "dcr_abc123def456",
  "client_secret": "generated_secret_xyz",
  "client_name": "Customer Application",
  "redirect_uris": ["https://customer-app.example.com/callback"],
  "grant_types": ["authorization_code", "refresh_token"],
  "response_types": ["code"],
  "token_endpoint_auth_method": "client_secret_basic",
  "client_id_issued_at": 1705312200,
  "client_secret_expires_at": 0
}
```

### AgentCard DCR Extension

The AgentCard advertises DCR support:

```json
{
  "name": "insights-agent",
  "extensions": {
    "dynamicClientRegistration": {
      "registrationEndpoint": "https://agent.example.com/oauth/register",
      "supportedGrantTypes": ["authorization_code", "refresh_token"],
      "supportedResponseTypes": ["code"],
      "supportedAuthMethods": ["client_secret_basic", "client_secret_post"]
    }
  }
}
```

## Procurement Integration

### Pub/Sub Notifications

Marketplace sends procurement events via Pub/Sub:

**Event Types:**

| Event | Description |
|-------|-------------|
| `ENTITLEMENT_CREATION_REQUESTED` | New subscription request |
| `ENTITLEMENT_ACTIVE` | Subscription activated |
| `ENTITLEMENT_PLAN_CHANGE_REQUESTED` | Plan upgrade/downgrade |
| `ENTITLEMENT_CANCELLED` | Subscription canceled |
| `ENTITLEMENT_PENDING_CANCELLATION` | Pending cancellation |
| `ENTITLEMENT_DELETED` | Subscription deleted |

**Message Format:**

```json
{
  "eventId": "evt_abc123",
  "eventType": "ENTITLEMENT_ACTIVE",
  "entitlement": {
    "id": "entitlements/abc123",
    "account": "accounts/user@example.com",
    "provider": "providers/insights-agent",
    "product": "products/insights-agent",
    "plan": "plans/professional",
    "state": "ENTITLEMENT_ACTIVE",
    "createTime": "2024-01-15T10:00:00Z"
  }
}
```

### Handling Entitlements

```python
# Example procurement handler
async def handle_procurement_event(message: dict):
    event_type = message["eventType"]
    entitlement = message["entitlement"]

    if event_type == "ENTITLEMENT_ACTIVE":
        # Activate subscription
        await activate_subscription(
            account=entitlement["account"],
            plan=entitlement["plan"]
        )
    elif event_type == "ENTITLEMENT_CANCELLED":
        # Deactivate subscription
        await deactivate_subscription(
            account=entitlement["account"]
        )
```

## Usage Metering

### Metrics Tracked

| Metric | Description | Unit |
|--------|-------------|------|
| `request_count` | Number of API requests | requests |
| `token_usage` | LLM tokens consumed | tokens |
| `tool_calls` | MCP tool invocations | calls |
| `compute_time` | Processing time | seconds |

### Reporting to Service Control

Usage is reported to Google Cloud Service Control API:

```python
from google.cloud import servicecontrol_v1

async def report_usage(
    consumer_id: str,
    operation_id: str,
    metrics: dict
):
    client = servicecontrol_v1.ServiceControllerAsyncClient()

    await client.report(
        service_name="insights-agent.endpoints.project.cloud.goog",
        operations=[
            servicecontrol_v1.Operation(
                operation_id=operation_id,
                consumer_id=f"project:{consumer_id}",
                labels={"cloud.googleapis.com/location": "us-central1"},
                metric_value_sets=[
                    servicecontrol_v1.MetricValueSet(
                        metric_name="serviceruntime.googleapis.com/api/request_count",
                        metric_values=[
                            servicecontrol_v1.MetricValue(int64_value=metrics["requests"])
                        ]
                    )
                ]
            )
        ]
    )
```

### Reporting Interval

Usage is reported:
- **Real-time**: For critical operations (authentication, etc.)
- **Batched**: Every hour for general usage
- **On shutdown**: Flush remaining metrics

## Subscription Tiers

### Tier Configuration

| Tier | Requests/min | Requests/hour | Tokens/day | Features |
|------|-------------|---------------|------------|----------|
| Free | 10 | 100 | 10,000 | Basic queries |
| Professional | 60 | 1,000 | 100,000 | All features |
| Enterprise | 300 | 10,000 | 1,000,000 | Priority support |

### Rate Limit Enforcement

Rate limits are enforced based on subscription tier:

```python
async def check_rate_limit(client_id: str) -> bool:
    # Get subscription tier for client
    tier = await get_subscription_tier(client_id)

    # Get tier limits
    limits = TIER_LIMITS[tier]

    # Check against Redis counters
    current = await redis.incr(f"rate:{client_id}:minute")
    if current > limits["requests_per_minute"]:
        return False

    return True
```

## Setup Instructions

### 1. Enable Required APIs

```bash
gcloud services enable \
  cloudcommerceprocurement.googleapis.com \
  servicecontrol.googleapis.com \
  servicemanagement.googleapis.com \
  pubsub.googleapis.com
```

### 2. Create Pub/Sub Subscription

```bash
# Create topic for procurement events
gcloud pubsub topics create marketplace-entitlements

# Create push subscription to your service
gcloud pubsub subscriptions create marketplace-entitlements-sub \
  --topic=marketplace-entitlements \
  --push-endpoint=https://your-agent.run.app/webhooks/procurement
```

### 3. Configure Service Control

```bash
# Set service name
export SERVICE_CONTROL_SERVICE_NAME=insights-agent.endpoints.PROJECT_ID.cloud.goog

# Grant service account permissions
gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="serviceAccount:insights-agent@PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/servicecontrol.serviceController"
```

### 4. Register with Marketplace

1. Go to [Cloud Partner Portal](https://console.cloud.google.com/partner)
2. Create a new product listing
3. Configure pricing plans
4. Set up procurement integration
5. Submit for review

## Testing

### Test DCR Locally

```bash
# Start the agent
python -m insights_agent.main

# Test DCR endpoint
curl -X POST http://localhost:8000/oauth/register \
  -H "Content-Type: application/json" \
  -d '{
    "client_name": "Test Client",
    "redirect_uris": ["http://localhost:3000/callback"],
    "grant_types": ["authorization_code"]
  }'
```

### Test Procurement Events

```bash
# Publish test event
gcloud pubsub topics publish marketplace-entitlements \
  --message='{
    "eventType": "ENTITLEMENT_ACTIVE",
    "entitlement": {
      "account": "test@example.com",
      "plan": "professional"
    }
  }'
```

### Test Usage Reporting

```bash
# View reported metrics
gcloud logging read \
  'resource.type="cloud_run_revision" AND textPayload:"usage_reported"' \
  --project=PROJECT_ID
```

## Troubleshooting

### DCR Failures

| Error | Cause | Solution |
|-------|-------|----------|
| 400 Invalid redirect_uri | URI not HTTPS | Use HTTPS URIs in production |
| 401 Unauthorized | Missing/invalid token | Check request authentication |
| 409 Client exists | Duplicate registration | Use existing credentials |

### Procurement Issues

| Issue | Cause | Solution |
|-------|-------|----------|
| Missing events | Subscription not configured | Verify Pub/Sub subscription |
| Event processing failed | Handler error | Check logs for exceptions |
| Entitlement not found | Sync delay | Wait and retry |

### Usage Reporting Issues

| Issue | Cause | Solution |
|-------|-------|----------|
| Metrics not appearing | Service account permissions | Grant servicecontrol.serviceController |
| Quota exceeded | Too many report calls | Batch metrics before reporting |
| Invalid operation | Malformed request | Validate operation structure |
