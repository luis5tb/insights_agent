# Red Hat Insights Agent

An A2A-ready agent for Red Hat Insights built with Google Agent Development Kit (ADK).

## Overview

This agent provides AI-powered access to Red Hat Insights services, enabling natural language interaction with:

- **Advisor**: System configuration assessment and recommendations
- **Inventory**: System management and tracking
- **Vulnerability**: Security threat analysis and CVE information
- **Remediations**: Issue resolution guidance and playbook management
- **Planning**: RHEL upgrade and migration planning
- **Image Builder**: Custom RHEL image creation

## Features

- Built with Google ADK and Gemini 2.5 Flash
- A2A protocol support with SSE streaming for multi-agent ecosystems
- OAuth 2.0 authentication via Red Hat SSO
- Dynamic Client Registration (DCR) with Red Hat SSO (Keycloak)
- Google Cloud Marketplace integration (Gemini Enterprise)
- PostgreSQL persistence for production deployments
- Usage tracking and reporting to Google Cloud Service Control
- Global rate limiting (requests per minute/hour)
- Integrated MCP server for Red Hat Insights API access

## Architecture

The system consists of **two separate services**:

```
                        Google Cloud Marketplace
                                 │
           ┌─────────────────────┴─────────────────────┐
           │ Pub/Sub Events                            │ DCR Requests
           ▼                                           ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                  Marketplace Handler (Port 8001)                         │
│                  ────────────────────────────────                        │
│  - Always running to receive Pub/Sub provisioning events                │
│  - Hybrid /dcr endpoint (Pub/Sub + DCR)                                 │
│  - Creates OAuth clients in Red Hat SSO via DCR                         │
│  - Stores accounts, entitlements, clients in PostgreSQL                 │
└─────────────────────────────────────────────────────────────────────────┘
                                 │
                                 │ Shared PostgreSQL
                                 ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                     Insights Agent (Port 8000)                           │
│                     ──────────────────────────                           │
│  ┌─────────────────────┐      ┌─────────────────────────────┐           │
│  │   Insights Agent    │ HTTP │   Red Hat Insights MCP      │           │
│  │   (Gemini + ADK)    │◄────►│   Server (Sidecar)          │           │
│  │                     │      │                             │           │
│  │   - A2A protocol    │      │   - Advisor, Inventory      │           │
│  │   - OAuth 2.0       │      │   - Vulnerability, Patch    │           │
│  │   - Session mgmt    │      │   - Remediations            │           │
│  └─────────────────────┘      └──────────────┬──────────────┘           │
└───────────────────────────────────────────────┼─────────────────────────┘
                                                │
                                                ▼
                                       ┌───────────────────┐
                                       │ console.redhat.com│
                                       │ (Insights APIs)   │
                                       └───────────────────┘
```

### Service Responsibilities

| Service | Port | Purpose | Scaling |
|---------|------|---------|---------|
| **Marketplace Handler** | 8001 | Pub/Sub events, DCR, provisioning | Always on (minScale=1) |
| **Insights Agent** | 8000 | A2A queries, user interactions, MCP | Scale to zero when idle |

### Deployment Order

1. **Deploy Marketplace Handler first** - Must be running to receive provisioning events
2. **Deploy Agent after provisioning** - Can be deployed when customers are ready

See [docs/architecture.md](docs/architecture.md) for detailed architecture documentation.

## Quick Start

### Prerequisites

- Python 3.11+
- Google API key or Vertex AI access
- Red Hat Insights service account credentials

### Installation

1. Clone the repository:
   ```bash
   git clone <repository-url>
   cd insights-agent
   ```

2. Create a virtual environment:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # Linux/macOS
   # or
   .venv\Scripts\activate     # Windows
   ```

3. Install dependencies:
   ```bash
   pip install -e ".[dev]"
   ```

4. Configure environment:
   ```bash
   cp .env.example .env
   # Edit .env with your credentials
   ```

### Running the Agent

The agent requires the Red Hat Insights MCP server to be running to access Insights APIs. Choose one of the following approaches:

#### Option 1: Development Mode (with MCP Server)

1. **Start the MCP server** in a separate terminal:
   ```bash
   # Start the MCP server container
   # Note: Credentials are passed by the agent via HTTP headers, not env vars
   podman run -d --name insights-mcp \
     -p 8080:8080 \
     quay.io/redhat-services-prod/insights-management-tenant/insights-mcp/red-hat-lightspeed-mcp:latest \
     http --port 8080 --host 0.0.0.0
   ```

2. **Run the agent** using one of these methods:

   **Development UI (ADK Web):**
   ```bash
   adk web agents
   ```

   **Terminal Mode:**
   ```bash
   adk run agents/rh_insights_agent
   ```

   **API Server:**
   ```bash
   python -m insights_agent.main
   ```

#### Option 2: Full Stack with Podman Pod

For production-like deployment with all services (agent, MCP server, database):

```bash
# Deploy secrets first (see Container Deployment for setup)
podman kube play deploy/podman/my-secrets.yaml

# Start all services
podman kube play \
  --configmap deploy/podman/insights-agent-configmap.yaml \
  deploy/podman/insights-agent-pod.yaml

# Access the agent at http://localhost:8000
```

See [Container Deployment](#container-deployment) for full details.

#### Option 3: Development without MCP (Limited)

If MCP credentials are not configured, the agent will start without tools (limited functionality):

```bash
# Unset MCP credentials to skip MCP connection
unset LIGHTSPEED_CLIENT_ID
unset LIGHTSPEED_CLIENT_SECRET

# Run agent (will work but without Insights API access)
adk web agents
```

## Configuration

See `.env.example` for all available configuration options.

### Required Environment Variables

| Variable | Description |
|----------|-------------|
| `GOOGLE_API_KEY` | Google AI Studio API key |
| `LIGHTSPEED_CLIENT_ID` | Red Hat Insights service account ID |
| `LIGHTSPEED_CLIENT_SECRET` | Red Hat Insights service account secret |
| `RED_HAT_SSO_CLIENT_ID` | OAuth client ID for Red Hat SSO |
| `RED_HAT_SSO_CLIENT_SECRET` | OAuth client secret for Red Hat SSO |

### Obtaining Credentials

#### Lightspeed Service Account (for MCP Server)

The MCP server uses Lightspeed service account credentials to authenticate with console.redhat.com APIs. To obtain these:

1. Go to [console.redhat.com](https://console.redhat.com)
2. Navigate to **Settings** → **Integrations** → **Red Hat Lightspeed**
3. Create a new service account
4. Copy the **Client ID** and **Client Secret**

These credentials allow the MCP server to access:
- Advisor (system recommendations)
- Inventory (registered systems)
- Vulnerability (CVE information)
- Remediations (playbook management)
- Patch (system updates)
- Image Builder (custom RHEL images)

#### Red Hat SSO OAuth Credentials

For user authentication via OAuth 2.0:

1. Register your application with Red Hat SSO
2. Configure redirect URIs for your deployment
3. Obtain the client ID and secret

## Project Structure

```
insights_agent/
├── agent.py                 # ADK CLI entry point
├── pyproject.toml          # Project configuration
├── .env.example            # Environment template
├── Containerfile           # Agent container build (UBI 9)
├── Containerfile.marketplace-handler  # Handler container build
├── Makefile                # Development commands
├── docs/                   # Documentation
│   ├── architecture.md     # System architecture (two-service)
│   ├── architecture-dcr.md # DCR and provisioning flows
│   ├── authentication.md   # OAuth 2.0 guide
│   ├── api.md              # API reference
│   ├── configuration.md    # Config reference
│   ├── marketplace.md      # GCP Marketplace integration
│   └── troubleshooting.md  # Troubleshooting guide
├── deploy/
│   ├── cloudrun/           # Cloud Run deployment
│   │   ├── service.yaml           # Agent service config
│   │   ├── marketplace-handler.yaml  # Handler service config
│   │   └── deploy.sh              # Deploy script (--service all|handler|agent)
│   └── podman/             # Podman/Kubernetes deployment
│       ├── marketplace-handler-pod.yaml  # Handler pod (start first)
│       ├── insights-agent-pod.yaml       # Agent pod
│       ├── insights-agent-configmap.yaml
│       └── insights-agent-secret.yaml
└── src/
    └── insights_agent/
        ├── api/                # A2A endpoints and AgentCard
        │   └── a2a/            # A2A protocol setup
        ├── auth/               # OAuth 2.0 authentication
        ├── config/             # Settings management
        ├── core/               # Agent definition (ADK)
        ├── db/                 # Database models (SQLAlchemy)
        ├── dcr/                # Dynamic Client Registration
        │   ├── keycloak_client.py  # Red Hat SSO DCR client
        │   └── service.py          # DCR business logic
        ├── marketplace/        # Google Marketplace integration
        │   ├── service.py          # Procurement API
        │   └── repository.py       # PostgreSQL persistence
        ├── marketplace_handler/  # Separate handler service
        │   ├── app.py              # FastAPI app (port 8001)
        │   └── router.py           # Hybrid /dcr endpoint
        ├── metering/           # Usage tracking
        └── tools/              # MCP integration
```

## Documentation

Comprehensive documentation is available in the [docs/](docs/) directory:

- [Architecture Overview](docs/architecture.md) - Two-service architecture and data flows
- [DCR Architecture](docs/architecture-dcr.md) - Dynamic Client Registration and provisioning flows
- [MCP Server Integration](docs/mcp-integration.md) - Red Hat Insights MCP server setup
- [Authentication Guide](docs/authentication.md) - OAuth 2.0 and JWT validation
- [API Reference](docs/api.md) - Endpoints and examples
- [Configuration Reference](docs/configuration.md) - All environment variables
- [Marketplace Integration](docs/marketplace.md) - GCP Marketplace, DCR, billing
- [Troubleshooting Guide](docs/troubleshooting.md) - Common issues and solutions

## Container Deployment (Podman)

The system is deployed as **two separate pods**, each with its own PostgreSQL database:

1. **Marketplace Handler Pod** (start first):
   - **marketplace-handler**: Handles Pub/Sub events and DCR requests
   - **postgres**: PostgreSQL database for marketplace data (orders, entitlements, DCR clients)

2. **Insights Agent Pod** (start after handler):
   - **insights-agent**: Main A2A agent (Gemini + Google ADK)
   - **insights-mcp**: Red Hat Insights MCP server
   - **session-postgres**: PostgreSQL database for agent sessions (ADK session persistence)
   - **a2a-inspector**: Web UI for agent interaction (optional)

### Prerequisites

- Podman 4.0+
- Access to Red Hat container registry (for RHEL-based images)
- Red Hat Insights Lightspeed service account credentials
- Google API key or Vertex AI access

### Build the Container Images

```bash
# Build the marketplace handler image
podman build -t localhost/marketplace-handler:latest -f Containerfile.marketplace-handler .

# Build the agent image
podman build -t localhost/insights-agent:latest -f Containerfile .

# (Optional) Build the A2A Inspector for web UI
git clone https://github.com/a2aproject/a2a-inspector.git /tmp/a2a-inspector
podman build -t localhost/a2a-inspector:latest /tmp/a2a-inspector
```

### Configure Environment

1. Create the config directory:
   ```bash
   mkdir -p config
   ```

2. If using Vertex AI, copy your credentials:
   ```bash
   cp /path/to/vertex-credentials.json config/
   ```

3. Create your secrets file with credentials:
   ```bash
   # Copy the template
   cp deploy/podman/insights-agent-secret.yaml deploy/podman/my-secrets.yaml

   # Edit with your actual credentials (plain text, no encoding needed)
   # IMPORTANT: Never commit my-secrets.yaml to version control!
   ```

   Edit `deploy/podman/my-secrets.yaml` and fill in:

   **API Credentials:**
   - `GOOGLE_API_KEY`: Your Google AI Studio API key
   - `LIGHTSPEED_CLIENT_ID`: Red Hat Insights service account ID
   - `LIGHTSPEED_CLIENT_SECRET`: Red Hat Insights service account secret
   - `RED_HAT_SSO_CLIENT_ID`: OAuth client ID for Red Hat SSO
   - `RED_HAT_SSO_CLIENT_SECRET`: OAuth client secret for Red Hat SSO

   **Database Passwords:**
   - `MARKETPLACE_DB_PASSWORD`: Password for marketplace PostgreSQL (default: `insights`)
   - `SESSION_DB_PASSWORD`: Password for session PostgreSQL (default: `sessions`)

   **Database URLs:**
   - `MARKETPLACE_DATABASE_URL`: Marketplace DB URL for marketplace-handler pod (uses `localhost:5432` since PostgreSQL is in the same pod)
   - `DATABASE_URL`: Marketplace DB URL for insights-agent pod (uses `host.containers.internal:5432` to reach the marketplace-handler pod's PostgreSQL)
   - `SESSION_DATABASE_URL`: Session DB URL for insights-agent pod (uses `localhost:5433` since session PostgreSQL is in the same pod)

4. (Optional) Customize configuration in `deploy/podman/insights-agent-configmap.yaml`:
   - Database users and names (`MARKETPLACE_DB_USER`, `SESSION_DB_USER`, etc.)
   - Agent settings, logging, rate limiting
   - MCP server configuration

### Run the Pods

```bash
# First, deploy the secrets (creates a Kubernetes Secret in podman)
podman kube play deploy/podman/my-secrets.yaml

# Start the marketplace handler FIRST (contains PostgreSQL)
podman kube play \
  --configmap deploy/podman/insights-agent-configmap.yaml \
  deploy/podman/marketplace-handler-pod.yaml

# Then start the agent pod (connects to handler's PostgreSQL)
podman kube play \
  --configmap deploy/podman/insights-agent-configmap.yaml \
  deploy/podman/insights-agent-pod.yaml

# View pod status
podman pod ps

# View container logs
podman logs marketplace-handler-marketplace-handler  # Handler logs
podman logs marketplace-handler-postgres             # Marketplace PostgreSQL logs
podman logs insights-agent-pod-insights-agent        # Agent logs
podman logs insights-agent-pod-insights-mcp          # MCP server logs
podman logs insights-agent-pod-session-postgres      # Session PostgreSQL logs

# Stop and remove all resources (reverse order)
podman kube down deploy/podman/insights-agent-pod.yaml
podman kube down deploy/podman/marketplace-handler-pod.yaml
podman kube down deploy/podman/my-secrets.yaml
```

### Access the Services

**Marketplace Handler:**

| Service | URL | Description |
|---------|-----|-------------|
| Handler Health | http://localhost:8001/health | Handler health status |
| DCR Endpoint | http://localhost:8001/dcr | Pub/Sub + DCR hybrid endpoint |

**Insights Agent:**

| Service | URL | Description |
|---------|-----|-------------|
| Agent API | http://localhost:8000 | Main A2A endpoint |
| Health Check | http://localhost:8000/health | Agent health status |
| AgentCard | http://localhost:8000/.well-known/agent.json | A2A discovery |
| OAuth Callback | http://localhost:8000/oauth/callback | OAuth redirect |
| MCP Server | http://localhost:8081 | MCP server (internal) |
| A2A Inspector | http://localhost:8080 | Web UI for agent interaction |

### Using the A2A Inspector (Web UI)

The [A2A Inspector](https://github.com/a2aproject/a2a-inspector) provides a web-based interface for interacting with the agent, similar to `adk web` but designed for deployed agents.

**Features:**
- View the agent's AgentCard and capabilities
- Chat interface with streaming responses
- JSON-RPC 2.0 debug console to inspect raw messages
- A2A protocol spec compliance validation

**To use the Inspector:**

1. Build the inspector image (see [Build the Container Images](#build-the-container-images))
2. Start the pod as usual
3. Open http://localhost:8080 in your browser
4. Enter `http://localhost:8000` as the agent URL
5. The inspector will fetch the AgentCard and enable chat

> **Note:** If you don't need the web UI, you can skip building the inspector image. The pod will start with a warning about the missing image but other containers will work normally.

### Authentication Testing

The agent supports OAuth 2.0 authentication via Red Hat SSO. For local testing, you can use the OCM CLI to obtain a valid token.

#### Prerequisites

Install the OCM CLI from https://console.redhat.com/openshift/token

#### Obtaining a Token

1. **Login with browser-based authentication:**
   ```bash
   ocm login --use-auth-code
   ```
   This opens a browser window for Red Hat SSO authentication.

2. **Get the access token:**
   ```bash
   ocm token
   ```
   This prints the current access token.

#### Configure the Agent for OCM Tokens

Update your `deploy/podman/my-secrets.yaml` to use `ocm-cli` as the client ID (matching the token's audience):

```yaml
RED_HAT_SSO_CLIENT_ID: "ocm-cli"
```

Then redeploy the secrets and restart the agent pod.

#### Testing with the Token

**Option 1: A2A Inspector**

1. Open http://localhost:8080
2. Enter `http://localhost:8000` as the agent URL
3. Add the Authorization header with your token in the Inspector settings

**Option 2: curl**

```bash
# Get token
TOKEN=$(ocm token)

# Test the A2A endpoint
curl -X POST http://localhost:8000/ \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "method": "message/send",
    "params": {
      "message": {
        "role": "user",
        "parts": [{"type": "text", "text": "Show my systems"}]
      }
    },
    "id": "1"
  }'
```

#### Development Mode (Skip Authentication)

For development without real tokens, set `SKIP_JWT_VALIDATION: "true"` in the configmap. Any token will be accepted.

### Pod Services

**Marketplace Handler Pod:**

| Container | Port | Description |
|-----------|------|-------------|
| marketplace-handler | 8001 | Pub/Sub events and DCR endpoint |
| postgres | 5432 | PostgreSQL for marketplace data (orders, entitlements, DCR clients) |

**Insights Agent Pod:**

| Container | Port | Description |
|-----------|------|-------------|
| insights-agent | 8000 | Main A2A agent API |
| insights-mcp | 8081 | Red Hat Insights MCP server |
| session-postgres | 5433 | PostgreSQL for agent sessions (ADK session persistence) |
| a2a-inspector | 8080 | Web UI for agent interaction (optional) |

### Database Architecture

The system uses **two separate PostgreSQL databases** for security isolation:

| Database | Pod | Port | Purpose |
|----------|-----|------|---------|
| Marketplace DB | marketplace-handler | 5432 | Orders, entitlements, DCR clients |
| Session DB | insights-agent | 5433 | ADK agent sessions |

This separation ensures:
- Agent sessions cannot access marketplace/auth data
- Compromised agents cannot access DCR credentials or order information
- Different retention and backup policies can be applied to each database

### How the MCP Server Works

The MCP server runs as a sidecar container and provides tools for the agent to interact with Red Hat Insights APIs:

1. **Agent receives a request** (e.g., "Show me my system vulnerabilities")
2. **Agent calls MCP tools** via HTTP to the MCP server (localhost:8081), passing credentials in headers
3. **MCP server authenticates** with console.redhat.com using the credentials from headers
4. **MCP server calls Insights APIs** and returns results to the agent
5. **Agent formats the response** and returns it to the user

The Lightspeed credentials (`LIGHTSPEED_CLIENT_ID` and `LIGHTSPEED_CLIENT_SECRET`) are configured on the **agent** container, which passes them to the MCP server via HTTP headers on each request. The MCP server itself does not need credentials configured.

### Persistent Storage

By default, both PostgreSQL databases use `emptyDir` volumes and data is lost when the pods are removed. To persist data:

1. **Marketplace Database**: Edit `deploy/podman/marketplace-handler-pod.yaml` and change the `postgres-data` volume from `emptyDir` to `hostPath`
2. **Session Database**: Edit `deploy/podman/insights-agent-pod.yaml` and change the `session-pgdata` volume from `emptyDir` to `hostPath`

Example hostPath configuration:
```yaml
volumes:
  - name: postgres-data  # or session-pgdata
    hostPath:
      path: ./data/pgdata
      type: DirectoryOrCreate
```

## Google Cloud Run Deployment

For production deployment to Google Cloud Run, see [deploy/cloudrun/README.md](deploy/cloudrun/README.md).

The system deploys as **two separate Cloud Run services**:
- **marketplace-handler**: Always running (minScale=1) for Pub/Sub events
- **insights-agent**: Scales to zero when idle

Quick deploy:

```bash
# Set up GCP project
export GOOGLE_CLOUD_PROJECT="your-project-id"
export GOOGLE_CLOUD_LOCATION="us-central1"

# Run setup script
./deploy/cloudrun/setup.sh

# Deploy both services
./deploy/cloudrun/deploy.sh --service all --build --allow-unauthenticated

# Or deploy individually:
./deploy/cloudrun/deploy.sh --service handler --allow-unauthenticated
./deploy/cloudrun/deploy.sh --service agent --allow-unauthenticated
```

## License

Apache License 2.0
