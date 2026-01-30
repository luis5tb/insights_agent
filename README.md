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
- A2A protocol support for multi-agent ecosystems
- OAuth 2.0 authentication via Red Hat SSO
- Dynamic Client Registration (DCR) for Google Marketplace
- Usage metering and reporting to Google Cloud
- Rate limiting and throttling per subscription tier
- Integrated MCP server for Red Hat Insights API access

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         Pod / Container                          │
│  ┌─────────────────────┐      ┌─────────────────────────────┐  │
│  │   Insights Agent    │ HTTP │   Red Hat Insights MCP      │  │
│  │   (Gemini + ADK)    │◄────►│   Server                    │  │
│  │                     │:8080 │                             │  │
│  │   Port 8000         │      │   Authenticates with        │  │
│  └─────────────────────┘      │   console.redhat.com        │  │
│           │                   └──────────────┬──────────────┘  │
│           │                                  │                  │
└───────────┼──────────────────────────────────┼──────────────────┘
            │                                  │
            ▼                                  ▼
    ┌───────────────┐                 ┌───────────────────┐
    │   Clients     │                 │ console.redhat.com│
    │   (A2A)       │                 │ (Insights APIs)   │
    └───────────────┘                 └───────────────────┘
```

The agent uses the MCP server as a sidecar to access Red Hat Insights APIs. The MCP server handles authentication with console.redhat.com using Lightspeed service account credentials.

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

For production-like deployment with all services (agent, MCP server, database, Redis):

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
├── Containerfile           # Container build (UBI 9)
├── Makefile                # Development commands
├── docs/                   # Documentation
│   ├── architecture.md     # System architecture
│   ├── authentication.md   # OAuth 2.0 guide
│   ├── api.md              # API reference
│   ├── configuration.md    # Config reference
│   ├── marketplace.md      # GCP Marketplace integration
│   └── troubleshooting.md  # Troubleshooting guide
├── deploy/
│   ├── cloudrun/           # Cloud Run deployment
│   └── podman/             # Podman/Kubernetes deployment
│       ├── insights-agent-pod.yaml
│       ├── insights-agent-configmap.yaml
│       └── insights-agent-secret.yaml
└── src/
    └── insights_agent/
        ├── api/            # A2A endpoints and AgentCard
        ├── auth/           # OAuth 2.0 and DCR
        ├── config/         # Settings management
        ├── core/           # Agent definition
        ├── db/             # Database models
        ├── metering/       # Usage tracking
        └── tools/          # MCP integration
```

## Documentation

Comprehensive documentation is available in the [docs/](docs/) directory:

- [Architecture Overview](docs/architecture.md) - System design and components
- [MCP Server Integration](docs/mcp-integration.md) - Red Hat Insights MCP server setup
- [Authentication Guide](docs/authentication.md) - OAuth 2.0 and JWT validation
- [API Reference](docs/api.md) - Endpoints and examples
- [Configuration Reference](docs/configuration.md) - All environment variables
- [Marketplace Integration](docs/marketplace.md) - GCP Marketplace, DCR, billing
- [Troubleshooting Guide](docs/troubleshooting.md) - Common issues and solutions

## Container Deployment (Podman)

The agent is deployed as a pod containing multiple containers:
- **insights-agent**: Main A2A agent (Gemini + Google ADK)
- **insights-mcp**: Red Hat Insights MCP server for console.redhat.com API access
- **postgres**: PostgreSQL database
- **redis**: Redis for rate limiting and caching

### Prerequisites

- Podman 4.0+
- Access to Red Hat container registry (for RHEL-based images)
- Red Hat Insights Lightspeed service account credentials
- Google API key or Vertex AI access

### Build the Container Image

```bash
podman build -t localhost/insights-agent:latest -f Containerfile .
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
   - `GOOGLE_API_KEY`: Your Google AI Studio API key
   - `LIGHTSPEED_CLIENT_ID`: Red Hat Insights service account ID
   - `LIGHTSPEED_CLIENT_SECRET`: Red Hat Insights service account secret
   - `RED_HAT_SSO_CLIENT_ID`: OAuth client ID for Red Hat SSO
   - `RED_HAT_SSO_CLIENT_SECRET`: OAuth client secret for Red Hat SSO

4. (Optional) Customize configuration in `deploy/podman/insights-agent-configmap.yaml`

### Run the Pod

```bash
# First, deploy the secrets (creates a Kubernetes Secret in podman)
podman kube play deploy/podman/my-secrets.yaml

# Then start the pod with ConfigMap
podman kube play \
  --configmap deploy/podman/insights-agent-configmap.yaml \
  deploy/podman/insights-agent-pod.yaml

# View pod status
podman pod ps

# View container logs
podman logs insights-agent-pod-insights-agent   # Agent logs
podman logs insights-agent-pod-insights-mcp     # MCP server logs

# Stop and remove all resources
podman kube down deploy/podman/insights-agent-pod.yaml
podman kube down deploy/podman/my-secrets.yaml
```

### Access the Services

| Service | URL | Description |
|---------|-----|-------------|
| Agent API | http://localhost:8000 | Main agent endpoint |
| Health Check | http://localhost:8000/health | Agent health status |
| AgentCard | http://localhost:8000/.well-known/agent.json | A2A discovery |
| OAuth Authorize | http://localhost:8000/oauth/authorize | OAuth login |
| MCP Server | http://localhost:8080 | MCP server (internal) |

### Pod Services

| Container | Port | Description |
|-----------|------|-------------|
| insights-agent | 8000 | Main A2A agent API |
| insights-mcp | 8080 | Red Hat Insights MCP server |
| postgres | 5432 | PostgreSQL database |
| redis | 6379 | Redis for rate limiting |

### How the MCP Server Works

The MCP server runs as a sidecar container and provides tools for the agent to interact with Red Hat Insights APIs:

1. **Agent receives a request** (e.g., "Show me my system vulnerabilities")
2. **Agent calls MCP tools** via HTTP to the MCP server (localhost:8080), passing credentials in headers
3. **MCP server authenticates** with console.redhat.com using the credentials from headers
4. **MCP server calls Insights APIs** and returns results to the agent
5. **Agent formats the response** and returns it to the user

The Lightspeed credentials (`LIGHTSPEED_CLIENT_ID` and `LIGHTSPEED_CLIENT_SECRET`) are configured on the **agent** container, which passes them to the MCP server via HTTP headers on each request. The MCP server itself does not need credentials configured.

### Persistent Storage

By default, database and Redis data use `emptyDir` and are lost when the pod is removed. To persist data, edit `deploy/podman/insights-agent-pod.yaml` and uncomment the `hostPath` volume configurations.

## Google Cloud Run Deployment

For production deployment to Google Cloud Run, see [deploy/cloudrun/README.md](deploy/cloudrun/README.md).

Quick deploy:

```bash
# Set up GCP project
export GOOGLE_CLOUD_PROJECT="your-project-id"
export GOOGLE_CLOUD_LOCATION="us-central1"

# Run setup script
./deploy/cloudrun/setup.sh

# Deploy
./deploy/cloudrun/deploy.sh
```

Or use the ADK CLI:

```bash
adk deploy cloud_run \
  --project=$GOOGLE_CLOUD_PROJECT \
  --region=$GOOGLE_CLOUD_LOCATION \
  .
```

## License

Apache License 2.0
