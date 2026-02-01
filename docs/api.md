# API Reference

This document describes the API endpoints provided by the Insights Agent.

## Base URL

- **Local Development**: `http://localhost:8000`
- **Production**: Your Cloud Run service URL

## Authentication

Most endpoints require a valid JWT access token from Red Hat SSO. Include the token in the Authorization header:

```
Authorization: Bearer <access_token>
```

See [Authentication](authentication.md) for details on obtaining tokens.

## A2A Protocol Endpoints

The agent implements the [A2A (Agent-to-Agent) protocol](https://google.github.io/A2A/) for interoperability with other agents.

### GET /.well-known/agent.json

Returns the AgentCard describing the agent's capabilities.

**Authentication**: Not required

**Response:**

```json
{
  "name": "insights-agent",
  "description": "Red Hat Insights Agent for infrastructure management",
  "url": "https://your-agent-url.com",
  "version": "0.1.0",
  "provider": {
    "organization": "Red Hat",
    "url": "https://www.redhat.com"
  },
  "capabilities": {
    "streaming": true,
    "pushNotifications": false,
    "stateTransitionHistory": true
  },
  "authentication": {
    "schemes": [
      {
        "scheme": "oauth2",
        "authorizationUrl": "https://your-agent-url.com/oauth/authorize",
        "tokenUrl": "https://your-agent-url.com/oauth/token",
        "scopes": {
          "openid": "OpenID Connect",
          "profile": "User profile",
          "email": "Email address"
        }
      }
    ]
  },
  "defaultInputModes": ["text"],
  "defaultOutputModes": ["text"],
  "skills": [
    {
      "id": "advisor",
      "name": "System Advisor",
      "description": "Get system recommendations and configuration assessment"
    },
    {
      "id": "inventory",
      "name": "System Inventory",
      "description": "Manage and query system inventory"
    },
    {
      "id": "vulnerability",
      "name": "Vulnerability Analysis",
      "description": "Analyze security vulnerabilities and CVEs"
    }
  ]
}
```

### POST /

Send a message to the agent using JSON-RPC 2.0 format. This is the main A2A endpoint.

**Authentication**: Required

**Methods:**
- `message/send` - Send a message and get response
- `message/stream` - Send a message and get streaming response (SSE)

**Request:**

```json
{
  "jsonrpc": "2.0",
  "method": "message/send",
  "params": {
    "message": {
      "role": "user",
      "parts": [
        {
          "type": "text",
          "text": "What systems have critical vulnerabilities?"
        }
      ]
    }
  },
  "id": "request-123"
}
```

**Response (Success):**

```json
{
  "jsonrpc": "2.0",
  "result": {
    "id": "task-456",
    "status": {
      "state": "completed"
    },
    "artifacts": [
      {
        "parts": [
          {
            "type": "text",
            "text": "I found 3 systems with critical vulnerabilities:\n\n1. server-01.example.com - CVE-2024-1234\n2. server-02.example.com - CVE-2024-5678\n3. database-01.example.com - CVE-2024-9012"
          }
        ]
      }
    ]
  },
  "id": "request-123"
}
```

**Response (Error):**

```json
{
  "jsonrpc": "2.0",
  "error": {
    "code": -32600,
    "message": "Invalid Request",
    "data": "Missing required field: message"
  },
  "id": "request-123"
}
```

### POST / (Streaming)

For streaming responses, use the `message/stream` method. The response is Server-Sent Events (SSE).

**Request:**

```json
{
  "jsonrpc": "2.0",
  "method": "message/stream",
  "params": {
    "message": {
      "role": "user",
      "parts": [
        {
          "type": "text",
          "text": "What systems have critical vulnerabilities?"
        }
      ]
    }
  },
  "id": "request-123"
}
```

**Response:**

SSE stream with A2A events:

```
event: message
data: {"jsonrpc":"2.0","result":{"status":{"state":"working"}},"id":"request-123"}

event: message
data: {"jsonrpc":"2.0","result":{"artifact":{"parts":[{"type":"text","text":"Found 3 systems..."}]}},"id":"request-123"}

event: message
data: {"jsonrpc":"2.0","result":{"status":{"state":"completed","final":true}},"id":"request-123"}
```

### GET /tasks/{task_id}

Get the status of a previously submitted task.

**Authentication**: Required

**Response:**

```json
{
  "id": "task-456",
  "status": {
    "state": "completed",
    "timestamp": "2024-01-15T10:30:00Z"
  },
  "artifacts": [
    {
      "parts": [
        {
          "type": "text",
          "text": "Task result..."
        }
      ]
    }
  ]
}
```

### DELETE /tasks/{task_id}

Cancel a running task.

**Authentication**: Required

**Response:**

```json
{
  "id": "task-456",
  "status": {
    "state": "canceled",
    "timestamp": "2024-01-15T10:31:00Z"
  }
}
```

## OAuth Endpoints

See [Authentication](authentication.md) for detailed OAuth documentation.

### GET /oauth/authorize

Initiate OAuth 2.0 authorization flow.

### GET /oauth/callback

Handle OAuth callback with authorization code.

### POST /oauth/token

Exchange authorization code or refresh token for access tokens.

### GET /oauth/userinfo

Get user information for authenticated user.

## Dynamic Client Registration

### POST /oauth/register

Register a new OAuth client dynamically (for marketplace integration).

**Authentication**: Signed JWT from Google Marketplace

**Request:**

```json
{
  "client_name": "My Application",
  "redirect_uris": ["https://myapp.example.com/callback"],
  "grant_types": ["authorization_code", "refresh_token"],
  "response_types": ["code"],
  "token_endpoint_auth_method": "client_secret_basic"
}
```

**Response:**

```json
{
  "client_id": "generated-client-id",
  "client_secret": "generated-client-secret",
  "client_name": "My Application",
  "redirect_uris": ["https://myapp.example.com/callback"],
  "grant_types": ["authorization_code", "refresh_token"],
  "response_types": ["code"],
  "token_endpoint_auth_method": "client_secret_basic",
  "client_id_issued_at": 1705312200,
  "client_secret_expires_at": 0
}
```

## Health Endpoints

### GET /health

Health check endpoint for load balancers and orchestrators.

**Authentication**: Not required

**Response:**

```json
{
  "status": "healthy",
  "agent": "insights-agent"
}
```

### GET /ready

Readiness check endpoint indicating the service is ready to accept requests.

**Authentication**: Not required

**Response:**

```json
{
  "status": "ready",
  "agent": "insights-agent"
}
```

## Error Codes

### HTTP Status Codes

| Code | Description |
|------|-------------|
| 200 | Success |
| 400 | Bad Request - Invalid input |
| 401 | Unauthorized - Missing or invalid authentication |
| 403 | Forbidden - Insufficient permissions |
| 404 | Not Found - Resource doesn't exist |
| 429 | Too Many Requests - Rate limit exceeded |
| 500 | Internal Server Error |
| 503 | Service Unavailable - Temporarily unavailable |

### JSON-RPC Error Codes

| Code | Message | Description |
|------|---------|-------------|
| -32700 | Parse error | Invalid JSON |
| -32600 | Invalid Request | Invalid JSON-RPC request |
| -32601 | Method not found | Unknown method |
| -32602 | Invalid params | Invalid method parameters |
| -32603 | Internal error | Internal server error |
| -32000 | Task not found | Referenced task doesn't exist |
| -32001 | Task canceled | Task was canceled |

## Usage Tracking

### GET /usage

Get aggregate usage statistics for the agent.

**Authentication**: Not required

**Response:**

```json
{
  "status": "ok",
  "usage": {
    "total_input_tokens": 12345,
    "total_output_tokens": 67890,
    "total_tokens": 80235,
    "total_requests": 150,
    "total_tool_calls": 75
  }
}
```

## Rate Limiting

The API enforces global rate limits to prevent abuse:

| Limit | Value | Window |
|-------|-------|--------|
| Requests per minute | 60 | 1 minute |
| Requests per hour | 1000 | 1 hour |

When rate limited, the API returns:

```json
{
  "error": "rate_limit_exceeded",
  "message": "Rate limit exceeded (per_minute)",
  "retry_after": 60
}
```

With headers:

```
Retry-After: 60
X-RateLimit-Limit: 60
X-RateLimit-Remaining: 0
```

## Examples

### Python

```python
import httpx

# Get access token (simplified - use OAuth flow in production)
token = "your-access-token"

# Send message to agent
response = httpx.post(
    "http://localhost:8000/",
    headers={"Authorization": f"Bearer {token}"},
    json={
        "jsonrpc": "2.0",
        "method": "message/send",
        "params": {
            "message": {
                "role": "user",
                "parts": [{"type": "text", "text": "List my systems"}]
            }
        },
        "id": "1"
    }
)

result = response.json()
print(result["result"]["artifacts"][0]["parts"][0]["text"])
```

### curl

```bash
# Get AgentCard
curl http://localhost:8000/.well-known/agent.json

# Health check
curl http://localhost:8000/health

# Get usage statistics
curl http://localhost:8000/usage

# Send message (with auth)
curl -X POST http://localhost:8000/ \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "method": "message/send",
    "params": {
      "message": {
        "role": "user",
        "parts": [{"type": "text", "text": "Show system recommendations"}]
      }
    },
    "id": "1"
  }'
```

### JavaScript

```javascript
const response = await fetch('http://localhost:8000/', {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${token}`,
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    jsonrpc: '2.0',
    method: 'message/send',
    params: {
      message: {
        role: 'user',
        parts: [{ type: 'text', text: 'What CVEs affect my systems?' }]
      }
    },
    id: '1'
  })
});

const result = await response.json();
console.log(result.result.artifacts[0].parts[0].text);
```
