# Configuration Reference

This document describes all configuration options for the Insights Agent.

## Environment Variables

Configuration is managed through environment variables. Copy `.env.example` to `.env` and customize for your environment.

### Google AI / Gemini

| Variable | Default | Description |
|----------|---------|-------------|
| `GOOGLE_GENAI_USE_VERTEXAI` | `FALSE` | Use Vertex AI instead of Google AI Studio |
| `GOOGLE_API_KEY` | - | Google AI Studio API key (required if not using Vertex AI) |
| `GOOGLE_CLOUD_PROJECT` | - | GCP project ID (required for Vertex AI) |
| `GOOGLE_CLOUD_LOCATION` | `us-central1` | GCP region for Vertex AI |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Gemini model to use |

**Using Google AI Studio:**

```bash
GOOGLE_GENAI_USE_VERTEXAI=FALSE
GOOGLE_API_KEY=your-api-key
```

**Using Vertex AI:**

```bash
GOOGLE_GENAI_USE_VERTEXAI=TRUE
GOOGLE_CLOUD_PROJECT=your-project-id
GOOGLE_CLOUD_LOCATION=us-central1
```

### Red Hat SSO / OAuth 2.0

| Variable | Default | Description |
|----------|---------|-------------|
| `RED_HAT_SSO_ISSUER` | `https://sso.redhat.com/auth/realms/redhat-external` | SSO issuer URL |
| `RED_HAT_SSO_CLIENT_ID` | - | OAuth client ID |
| `RED_HAT_SSO_CLIENT_SECRET` | - | OAuth client secret |
| `RED_HAT_SSO_REDIRECT_URI` | `http://localhost:8000/oauth/callback` | OAuth redirect URI |
| `RED_HAT_SSO_JWKS_URI` | Auto-derived from issuer | JWKS endpoint URL |

**Example:**

```bash
RED_HAT_SSO_ISSUER=https://sso.redhat.com/auth/realms/redhat-external
RED_HAT_SSO_CLIENT_ID=my-client-id
RED_HAT_SSO_CLIENT_SECRET=my-client-secret
RED_HAT_SSO_REDIRECT_URI=https://myagent.example.com/oauth/callback
```

### Red Hat Insights MCP

The MCP server runs as a sidecar container and provides tools for accessing Red Hat Insights APIs. See [MCP Integration](mcp-integration.md) for details.

| Variable | Default | Description |
|----------|---------|-------------|
| `LIGHTSPEED_CLIENT_ID` | - | Insights service account client ID |
| `LIGHTSPEED_CLIENT_SECRET` | - | Insights service account client secret |
| `MCP_TRANSPORT_MODE` | `http` | MCP transport: `stdio`, `http`, or `sse` |
| `MCP_SERVER_URL` | `http://localhost:8080` | MCP server URL (use 8081 for Podman to avoid A2A Inspector conflict) |
| `MCP_READ_ONLY` | `true` | Enable read-only mode for MCP tools |

**Obtaining Lightspeed Credentials:**

1. Go to [console.redhat.com](https://console.redhat.com)
2. Navigate to **Settings** → **Integrations** → **Red Hat Lightspeed**
3. Create a service account
4. Copy the Client ID and Client Secret

**Development (stdio mode):**

```bash
# Agent spawns MCP server as subprocess
LIGHTSPEED_CLIENT_ID=your-service-account-id
LIGHTSPEED_CLIENT_SECRET=your-service-account-secret
MCP_TRANSPORT_MODE=stdio
MCP_READ_ONLY=true
```

**Production (http mode with sidecar):**

```bash
# Agent connects to MCP server sidecar via HTTP
LIGHTSPEED_CLIENT_ID=your-service-account-id
LIGHTSPEED_CLIENT_SECRET=your-service-account-secret
MCP_TRANSPORT_MODE=http
MCP_SERVER_URL=http://localhost:8081  # Use 8081 for Podman (8080 for Cloud Run)
MCP_READ_ONLY=true
```

### Agent Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `AGENT_PROVIDER_URL` | `https://localhost:8000` | Agent public URL (for AgentCard) |
| `AGENT_NAME` | `insights-agent` | Agent name |
| `AGENT_DESCRIPTION` | Red Hat Insights Agent... | Agent description |
| `AGENT_HOST` | `0.0.0.0` | Server bind address |
| `AGENT_PORT` | `8000` | Server port |

**Example:**

```bash
AGENT_PROVIDER_URL=https://insights-agent.example.com
AGENT_NAME=insights-agent
AGENT_HOST=0.0.0.0
AGENT_PORT=8000
```

### Database

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `sqlite+aiosqlite:///./insights_agent.db` | Database connection URL |

**SQLite (Development):**

```bash
DATABASE_URL=sqlite+aiosqlite:///./insights_agent.db
```

**PostgreSQL (Production):**

```bash
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/insights_agent
```

**Cloud SQL (GCP):**

```bash
DATABASE_URL=postgresql+asyncpg://user:password@/insights_agent?host=/cloudsql/project:region:instance
```

### Rate Limiting

Rate limiting uses in-memory sliding window algorithm. No external dependencies required.

| Variable | Default | Description |
|----------|---------|-------------|
| `RATE_LIMIT_REQUESTS_PER_MINUTE` | `60` | Max requests per minute |
| `RATE_LIMIT_REQUESTS_PER_HOUR` | `1000` | Max requests per hour |

**Example:**

```bash
RATE_LIMIT_REQUESTS_PER_MINUTE=120
RATE_LIMIT_REQUESTS_PER_HOUR=2000
```

See [Rate Limiting](rate-limiting.md) for details on the sliding window algorithm.

### Google Cloud Service Control

| Variable | Default | Description |
|----------|---------|-------------|
| `SERVICE_CONTROL_SERVICE_NAME` | - | Service name for usage reporting |
| `GOOGLE_APPLICATION_CREDENTIALS` | - | Path to service account key file |

**Example:**

```bash
SERVICE_CONTROL_SERVICE_NAME=insights-agent.endpoints.my-project.cloud.goog
GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json
```

### Usage Tracking

Usage tracking is built into the agent via the ADK plugin system. No configuration required for basic tracking.

| Variable | Default | Description |
|----------|---------|-------------|
| `LOG_LEVEL` | `INFO` | Set to `DEBUG` to see detailed usage logs |

Access usage statistics via the `/usage` endpoint. See [Usage Tracking and Metering](metering.md) for details on the plugin system and how to extend it.

### Logging

| Variable | Default | Description |
|----------|---------|-------------|
| `LOG_LEVEL` | `INFO` | Log level: DEBUG, INFO, WARNING, ERROR |
| `LOG_FORMAT` | `json` | Log format: `json` or `text` |

**Example:**

```bash
LOG_LEVEL=DEBUG
LOG_FORMAT=text  # Human-readable for development
```

### Development Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `DEBUG` | `false` | Enable debug mode (exposes /docs) |
| `SKIP_JWT_VALIDATION` | `false` | Skip JWT validation (dev only!) |

**Development:**

```bash
DEBUG=true
SKIP_JWT_VALIDATION=true
LOG_LEVEL=DEBUG
LOG_FORMAT=text
```

**Production:**

```bash
DEBUG=false
SKIP_JWT_VALIDATION=false
LOG_LEVEL=INFO
LOG_FORMAT=json
```

## Configuration Files

### .env.example

Complete template with all configuration options:

```bash
# Copy to .env and customize
cp .env.example .env
```

### pyproject.toml

Project metadata and dependencies. Modify to add/update dependencies:

```toml
[project]
dependencies = [
    "google-adk>=0.5.0",
    # Add more dependencies here
]
```

## Secret Management

### Local Development

Store secrets in `.env` file (not committed to git):

```bash
# .env
GOOGLE_API_KEY=your-api-key
RED_HAT_SSO_CLIENT_SECRET=your-secret
```

### Production (Google Secret Manager)

Create secrets:

```bash
echo -n "secret-value" | gcloud secrets create secret-name --data-file=-
```

Reference in Cloud Run:

```bash
gcloud run deploy service-name \
  --set-secrets="GOOGLE_API_KEY=google-api-key:latest"
```

### Kubernetes

Use Kubernetes secrets:

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: insights-agent-secrets
type: Opaque
stringData:
  GOOGLE_API_KEY: your-api-key
  RED_HAT_SSO_CLIENT_SECRET: your-secret
```

## Configuration Validation

The agent validates configuration at startup:

```python
from insights_agent.config import get_settings

settings = get_settings()
# Raises ValidationError if required fields missing
```

### Required Fields

These fields must be set for the agent to start:

- `GOOGLE_API_KEY` (if not using Vertex AI)
- `GOOGLE_CLOUD_PROJECT` (if using Vertex AI)
- `LIGHTSPEED_CLIENT_ID`
- `LIGHTSPEED_CLIENT_SECRET`

### Validation Errors

If configuration is invalid, the agent logs an error and exits:

```
ValidationError: 1 validation error for Settings
google_api_key
  Field required [type=missing, input_value={...}, input_type=dict]
```

## Environment-Specific Configuration

### Development

```bash
# .env.development
DEBUG=true
SKIP_JWT_VALIDATION=true
LOG_LEVEL=DEBUG
LOG_FORMAT=text
DATABASE_URL=sqlite+aiosqlite:///./dev.db
```

### Staging

```bash
# .env.staging
DEBUG=false
SKIP_JWT_VALIDATION=false
LOG_LEVEL=INFO
LOG_FORMAT=json
DATABASE_URL=postgresql+asyncpg://user:pass@staging-db:5432/insights
```

### Production

```bash
# Secrets managed via Secret Manager
DEBUG=false
SKIP_JWT_VALIDATION=false
LOG_LEVEL=INFO
LOG_FORMAT=json
# DATABASE_URL from Secret Manager
```
