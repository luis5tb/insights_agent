# Google Cloud Run Deployment

Deploy the Red Hat Insights Agent to Google Cloud Run for production use.

## Architecture

The deployment consists of **two separate Cloud Run services**:

```
                              Google Cloud Marketplace
                                       │
                 ┌─────────────────────┴─────────────────────┐
                 │                                           │
                 ▼                                           ▼
      ┌──────────────────────┐                ┌──────────────────────────────────┐
      │  Pub/Sub (Events)    │                │  Gemini Enterprise (DCR)         │
      └──────────┬───────────┘                └──────────────────┬───────────────┘
                 │                                               │
                 ▼                                               ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                    Marketplace Handler Service (Port 8001)                       │
│                    ───────────────────────────────────────                       │
│  - Always running (minScale=1) to receive Pub/Sub events                        │
│  - Handles account/entitlement approvals via Procurement API                    │
│  - Handles DCR requests (creates OAuth clients in Red Hat SSO)                  │
│  - Stores data in PostgreSQL                                                     │
└─────────────────────────────────────────────────────────────────────────────────┘
                 │
                 │ Shared PostgreSQL Database
                 ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                     Insights Agent Service (Port 8000)                           │
│                     ─────────────────────────────────────                        │
│  ┌─────────────────────┐      ┌─────────────────────────┐                       │
│  │   Insights Agent    │ HTTP │   Insights MCP Server   │                       │
│  │                     │◄────►│   (Sidecar, Port 8081)  │                       │
│  │   - Gemini 2.5      │      │                         │                       │
│  │   - A2A protocol    │      │   - Advisor tools       │                       │
│  │   - OAuth 2.0       │      │   - Inventory tools     │                       │
│  │                     │      │   - Vulnerability tools │                       │
│  └─────────────────────┘      └───────────┬─────────────┘                       │
│                                           │                                      │
└───────────────────────────────────────────┼──────────────────────────────────────┘
                                            │
                                            ▼
                                   ┌─────────────────┐
                                   │console.redhat.com│
                                   │ (Insights APIs) │
                                   └─────────────────┘
```

### Service Responsibilities

| Service | Port | Purpose | Scaling |
|---------|------|---------|---------|
| **Marketplace Handler** | 8001 | Pub/Sub events, DCR | Always on (minScale=1) |
| **Insights Agent** | 8000 | A2A queries, user interactions | Scale to zero |

### Deployment Order

1. **Deploy Marketplace Handler first** - Must be running to receive provisioning events
2. **Deploy Agent after provisioning** - Can be deployed when customers are ready to use the agent

The MCP server runs as a sidecar in the Agent service and authenticates with console.redhat.com using Lightspeed service account credentials stored in Secret Manager.

## Prerequisites

- [Google Cloud CLI](https://cloud.google.com/sdk/docs/install) installed and authenticated
- GCP project with billing enabled
- Red Hat Insights Lightspeed service account credentials
- Required permissions:
  - Cloud Run Admin
  - Cloud Build Editor
  - Secret Manager Admin
  - Service Account Admin

## Quick Start

### 1. Set Environment Variables

```bash
export GOOGLE_CLOUD_PROJECT="your-project-id"
export GOOGLE_CLOUD_LOCATION="us-central1"
export SERVICE_NAME="insights-agent"

# Optional: disable Pub/Sub marketplace integration
export ENABLE_MARKETPLACE="false"
```

### 2. Run Setup Script

The setup script enables required APIs, creates a service account, and sets up secrets:

```bash
./deploy/cloudrun/setup.sh
```

**Environment variables:**
| Variable | Default | Description |
|----------|---------|-------------|
| `GOOGLE_CLOUD_PROJECT` | (required) | GCP project ID |
| `GOOGLE_CLOUD_LOCATION` | `us-central1` | GCP region |
| `SERVICE_NAME` | `insights-agent` | Cloud Run service name |
| `ENABLE_MARKETPLACE` | `true` | Create Pub/Sub for marketplace integration |

### 3. Set Up Cloud SQL Database

Cloud Run requires PostgreSQL for production. Create a Cloud SQL instance with two databases:

```bash
# Create Cloud SQL instance (using smallest Enterprise tier)
gcloud sql instances create insights-agent-db \
  --database-version=POSTGRES_16 \
  --edition=ENTERPRISE \
  --tier=db-g1-small \
  --region=$GOOGLE_CLOUD_LOCATION \
  --project=$GOOGLE_CLOUD_PROJECT

# Create marketplace database and user
gcloud sql databases create insights_agent \
  --instance=insights-agent-db \
  --project=$GOOGLE_CLOUD_PROJECT

gcloud sql users create insights \
  --instance=insights-agent-db \
  --password=YOUR_MARKETPLACE_PASSWORD \
  --project=$GOOGLE_CLOUD_PROJECT

# Create session database and user
gcloud sql databases create agent_sessions \
  --instance=insights-agent-db \
  --project=$GOOGLE_CLOUD_PROJECT

gcloud sql users create sessions \
  --instance=insights-agent-db \
  --password=YOUR_SESSION_PASSWORD \
  --project=$GOOGLE_CLOUD_PROJECT

# Get the connection name for later use
CONNECTION_NAME=$(gcloud sql instances describe insights-agent-db \
  --project=$GOOGLE_CLOUD_PROJECT --format='value(connectionName)')
echo "Connection name: $CONNECTION_NAME"
```

### 4. Configure Secrets

Update the placeholder secrets with actual values:

```bash
# Google API Key (for Google AI Studio)
echo -n 'your-google-api-key' | \
  gcloud secrets versions add google-api-key --data-file=- --project=$GOOGLE_CLOUD_PROJECT

# Red Hat Insights Lightspeed credentials
# These are used by the MCP server to authenticate with console.redhat.com
# Obtain from: console.redhat.com → Settings → Integrations → Red Hat Lightspeed
echo -n 'your-client-id' | \
  gcloud secrets versions add lightspeed-client-id --data-file=- --project=$GOOGLE_CLOUD_PROJECT

echo -n 'your-client-secret' | \
  gcloud secrets versions add lightspeed-client-secret --data-file=- --project=$GOOGLE_CLOUD_PROJECT

# Red Hat SSO credentials
echo -n 'your-sso-client-id' | \
  gcloud secrets versions add redhat-sso-client-id --data-file=- --project=$GOOGLE_CLOUD_PROJECT

echo -n 'your-sso-client-secret' | \
  gcloud secrets versions add redhat-sso-client-secret --data-file=- --project=$GOOGLE_CLOUD_PROJECT

# DCR (Dynamic Client Registration) - Required for Gemini Enterprise integration
# Initial Access Token from Red Hat SSO (Keycloak) admin
echo -n 'your-initial-access-token' | \
  gcloud secrets versions add dcr-initial-access-token --data-file=- --project=$GOOGLE_CLOUD_PROJECT

# Fernet encryption key for DCR client secrets
# Generate with: python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'
echo -n 'your-fernet-key' | \
  gcloud secrets versions add dcr-encryption-key --data-file=- --project=$GOOGLE_CLOUD_PROJECT

# Database URLs (use CONNECTION_NAME from step 3)
# Marketplace database: stores orders, entitlements, DCR clients
echo -n "postgresql+asyncpg://insights:YOUR_MARKETPLACE_PASSWORD@/insights_agent?host=/cloudsql/$CONNECTION_NAME" | \
  gcloud secrets versions add database-url --data-file=- --project=$GOOGLE_CLOUD_PROJECT

# Session database: stores agent sessions (required for persistence)
echo -n "postgresql+asyncpg://sessions:YOUR_SESSION_PASSWORD@/agent_sessions?host=/cloudsql/$CONNECTION_NAME" | \
  gcloud secrets versions add session-database-url --data-file=- --project=$GOOGLE_CLOUD_PROJECT
```

### 5. Copy MCP Image to GCR

Cloud Run doesn't support Quay.io directly. Copy the MCP server image to GCR:

```bash
# Pull from Quay.io
docker pull quay.io/redhat-services-prod/insights-management-tenant/insights-mcp/red-hat-lightspeed-mcp:latest

# Tag and push to GCR
docker tag quay.io/redhat-services-prod/insights-management-tenant/insights-mcp/red-hat-lightspeed-mcp:latest \
  gcr.io/$GOOGLE_CLOUD_PROJECT/insights-mcp:latest
docker push gcr.io/$GOOGLE_CLOUD_PROJECT/insights-mcp:latest
```

### 6. Deploy

The deploy script supports deploying both services. The default (`yaml`) method is recommended
as it includes the MCP sidecar container for the agent.

```bash
# Build and deploy both services (recommended for first deployment)
./deploy/cloudrun/deploy.sh --build --service all --allow-unauthenticated

# Deploy only the marketplace handler
./deploy/cloudrun/deploy.sh --service handler --allow-unauthenticated

# Deploy only the agent with existing image
./deploy/cloudrun/deploy.sh --service agent --image gcr.io/my-project/insights-agent:v1.0
```

**Deploy script options:**

| Flag | Description |
|------|-------------|
| `--service <service>` | Which service to deploy: `all` (default), `handler`, `agent` |
| `--method <method>` | Deployment method: `yaml` (default), `adk`, `cloudbuild` |
| `--image <image>` | Container image for the agent (default: `gcr.io/$PROJECT_ID/insights-agent:latest`) |
| `--handler-image <image>` | Container image for the marketplace handler (default: `gcr.io/$PROJECT_ID/marketplace-handler:latest`) |
| `--mcp-image <image>` | Container image for the MCP server (default: `gcr.io/$PROJECT_ID/insights-mcp:latest`) |
| `--build` | Build the image(s) before deploying |
| `--with-ui` | Include the ADK web UI (only for `adk` method, agent only) |
| `--allow-unauthenticated` | Allow public access (required for A2A and Pub/Sub) |

**Service deployment:**

| Service | YAML Config | Description |
|---------|-------------|-------------|
| `handler` | `marketplace-handler.yaml` | Pub/Sub events, DCR requests |
| `agent` | `service.yaml` | A2A queries with MCP sidecar |
| `all` | Both | Deploy both services |

**Deployment methods:**

| Method | MCP Sidecar | Services | Description |
|--------|-------------|----------|-------------|
| `yaml` | ✅ Yes | All | Uses YAML configs with variable substitution (recommended) |
| `adk` | ❌ No | Agent only | Uses ADK CLI (does not support sidecars) |
| `cloudbuild` | ✅ Yes | Agent only | Uses Cloud Build with `cloudbuild.yaml` |

**Examples:**

```bash
# Deploy both services (production setup)
./deploy/cloudrun/deploy.sh --build --service all --allow-unauthenticated

# Deploy only marketplace handler (for receiving procurement events)
./deploy/cloudrun/deploy.sh --service handler --allow-unauthenticated

# Deploy only agent with custom image
./deploy/cloudrun/deploy.sh --service agent --image quay.io/myorg/insights-agent:latest

# Deploy with ADK CLI (agent only, no MCP sidecar - not recommended for production)
./deploy/cloudrun/deploy.sh --service agent --method adk --with-ui

# Deploy using Cloud Build (agent only)
./deploy/cloudrun/deploy.sh --service agent --method cloudbuild
```

## Deployment Options

### Using service.yaml (Recommended)

The `service.yaml` file defines both the agent and MCP sidecar containers:

```bash
# Build image first
gcloud builds submit --tag gcr.io/$GOOGLE_CLOUD_PROJECT/insights-agent:latest .

# Deploy using service.yaml
./deploy/cloudrun/deploy.sh --method yaml
```

Or manually:
```bash
# Substitute variables and deploy
sed -e "s|\${PROJECT_ID}|$GOOGLE_CLOUD_PROJECT|g" \
    -e "s|\${REGION}|$GOOGLE_CLOUD_LOCATION|g" \
    deploy/cloudrun/service.yaml | \
    gcloud run services replace - --region=$GOOGLE_CLOUD_LOCATION --project=$GOOGLE_CLOUD_PROJECT
```

### Using ADK CLI (No MCP Sidecar)

> **Warning**: ADK CLI does not support sidecar containers. The agent will not
> have access to Red Hat Insights tools. Use only for testing the agent framework.

```bash
./deploy/cloudrun/deploy.sh --method adk --with-ui
```

**ADK CLI options:**

| Option | Description |
|--------|-------------|
| `--with_ui` | Deploy with the ADK web UI for interactive testing |
| `--port` | Container port (default: 8080, we use 8000) |

### Using Cloud Build

```bash
./deploy/cloudrun/deploy.sh --method cloudbuild
```

Or manually:
```bash
gcloud builds submit \
  --config=cloudbuild.yaml \
  --project=$GOOGLE_CLOUD_PROJECT \
  --substitutions=_SERVICE_NAME=insights-agent,_REGION=us-central1,_MCP_IMAGE=quay.io/redhat-services-prod/insights-management-tenant/insights-mcp/red-hat-lightspeed-mcp:latest
```

## Service Configuration

### Agent Container

| Setting | Value | Description |
|---------|-------|-------------|
| CPU | 2 | vCPUs allocated |
| Memory | 2Gi | Memory limit |
| Port | 8000 | Container port |

### MCP Server Sidecar

| Setting | Value | Description |
|---------|-------|-------------|
| CPU | 1 | vCPUs allocated |
| Memory | 512Mi | Memory limit |
| Port | 8080 | Internal MCP port |
| Image | `gcr.io/$PROJECT_ID/insights-mcp:latest` | MCP server image (copied from Quay.io) |

### Copying the MCP Image to GCR

Cloud Run doesn't support pulling images directly from Quay.io. You must copy the MCP server image to Google Container Registry (GCR) before deploying:

```bash
# Pull from Quay.io locally
docker pull quay.io/redhat-services-prod/insights-management-tenant/insights-mcp/red-hat-lightspeed-mcp:latest

# Tag for GCR
docker tag quay.io/redhat-services-prod/insights-management-tenant/insights-mcp/red-hat-lightspeed-mcp:latest \
  gcr.io/$GOOGLE_CLOUD_PROJECT/insights-mcp:latest

# Push to GCR
docker push gcr.io/$GOOGLE_CLOUD_PROJECT/insights-mcp:latest
```

This step is required before running `deploy.sh`. The deploy script defaults to `gcr.io/$PROJECT_ID/insights-mcp:latest`.

**To update the MCP server**, repeat the above steps with a new tag or `:latest`.

**Costs (GCR):**
| Cost Type | Rate | Notes |
|-----------|------|-------|
| Storage | $0.026/GB/month | ~$0.005/month for a 200MB image |
| Network egress | Standard GCP rates | Free within same region |
| Requests | No charge | Pull requests are free |

### Customizing MCP Server Configuration

The MCP server configuration is hardcoded in `deploy/cloudrun/service.yaml` because Cloud Run does not support environment variable expansion in the `args` field (unlike Kubernetes/Podman).

**Current MCP server settings:**
```yaml
args:
  - "--readonly"      # Run in read-only mode
  - "http"            # Use HTTP transport
  - "--port"
  - "8080"            # Listen on port 8080
  - "--host"
  - "0.0.0.0"         # Bind to all interfaces
```

**To change MCP server settings:**

1. Edit `deploy/cloudrun/service.yaml` directly:
   ```bash
   vim deploy/cloudrun/service.yaml
   # Find the "insights-mcp" container section
   # Modify the args array as needed
   ```

2. Common customizations:
   - **Change port**: Modify `"8080"` to your desired port (also update `MCP_SERVER_URL` in the agent container env)
   - **Enable write operations**: Remove `"--readonly"` flag (not recommended for production)
   - **Change transport**: Modify `"http"` to `"sse"` or `"stdio"` (requires corresponding agent changes)

3. Redeploy after making changes:
   ```bash
   ./deploy/cloudrun/deploy.sh --service agent
   ```

**Note**: If you change the MCP server port, you must also update the `MCP_SERVER_URL` environment variable in the agent container to match.

### Alternative: Use Docker Hub

Instead of GCR, you can copy the image to Docker Hub (free storage, but has rate limits):

```bash
# Pull from Quay.io
docker pull quay.io/redhat-services-prod/insights-management-tenant/insights-mcp/red-hat-lightspeed-mcp:latest

# Tag for Docker Hub (replace YOUR_USERNAME with your Docker Hub username)
docker tag quay.io/redhat-services-prod/insights-management-tenant/insights-mcp/red-hat-lightspeed-mcp:latest \
  docker.io/YOUR_USERNAME/insights-mcp:latest

# Login and push to Docker Hub
docker login
docker push docker.io/YOUR_USERNAME/insights-mcp:latest

# Deploy with Docker Hub image
./deploy/cloudrun/deploy.sh --mcp-image docker.io/YOUR_USERNAME/insights-mcp:latest
```

**Docker Hub Rate Limits:**
| Account Type | Pull Limit | Cost |
|--------------|------------|------|
| Anonymous | 100 pulls / 6 hours | Free |
| Free (authenticated) | 200 pulls / 6 hours | Free |
| Pro | 5,000 pulls / day | $5/month |
| Team | Unlimited | $9/user/month |

**When to use Docker Hub:**
- Development or low-traffic deployments
- You already have a Docker Hub account

**When to use GCR (recommended for production):**
- Auto-scaling deployments (rate limits could cause failures)
- High availability requirements
- Cost is negligible (~$0.005/month)

### Scaling

| Setting | Value | Description |
|---------|-------|-------------|
| Min Instances | 0 | Scale to zero when idle |
| Max Instances | 10 | Maximum concurrent instances |
| Concurrency | 80 | Requests per instance |
| Timeout | 300s | Request timeout |

## How the MCP Server Works

The MCP server runs as a sidecar container alongside the agent:

1. **Agent Container** (port 8000): Handles A2A requests, uses Gemini for AI
2. **MCP Server Container** (port 8080): Provides tools for Red Hat Insights APIs

When the agent needs to access Insights data (e.g., system vulnerabilities, recommendations):
1. Agent calls MCP tools via HTTP to `localhost:8080`
2. MCP server authenticates with console.redhat.com using Lightspeed credentials
3. MCP server calls the appropriate Insights API
4. Results are returned to the agent for processing

### Credential Flow

```
Secret Manager                    MCP Server              console.redhat.com
     │                               │                           │
     │  LIGHTSPEED_CLIENT_ID         │                           │
     │  LIGHTSPEED_CLIENT_SECRET     │                           │
     ├──────────────────────────────►│                           │
     │                               │   OAuth2 Token Request    │
     │                               ├──────────────────────────►│
     │                               │   Access Token            │
     │                               │◄──────────────────────────┤
     │                               │   API Request + Token     │
     │                               ├──────────────────────────►│
     │                               │   API Response            │
     │                               │◄──────────────────────────┤
```

## Authentication

The agent uses **Red Hat SSO** for authentication. Requests to the A2A endpoint
(POST /) require a valid Bearer token issued by Red Hat SSO.

### Authentication Flow

```
┌─────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   Client    │     │  Insights Agent │     │  Red Hat SSO    │
└──────┬──────┘     └────────┬────────┘     └────────┬────────┘
       │                     │                       │
       │  1. GET /oauth/authorize                    │
       ├────────────────────►│                       │
       │                     │                       │
       │  2. Redirect to SSO                         │
       │◄────────────────────┤                       │
       │                     │                       │
       │  3. Login at SSO ──────────────────────────►│
       │                     │                       │
       │  4. Redirect with code                      │
       │◄───────────────────────────────────────────-┤
       │                     │                       │
       │  5. POST /oauth/token (code)                │
       ├────────────────────►│                       │
       │                     │  6. Exchange code     │
       │                     ├──────────────────────►│
       │                     │  7. Access token      │
       │                     │◄──────────────────────┤
       │  8. Token response  │                       │
       │◄────────────────────┤                       │
       │                     │                       │
       │  9. POST / (A2A) with Bearer token          │
       ├────────────────────►│                       │
       │                     │  10. Validate JWT     │
       │                     ├──────────────────────►│
       │  11. A2A Response   │                       │
       │◄────────────────────┤                       │
```

### Configuration

| Secret | Description |
|--------|-------------|
| `redhat-sso-client-id` | OAuth 2.0 client ID registered with Red Hat SSO |
| `redhat-sso-client-secret` | OAuth 2.0 client secret |

### Development Mode

Set `SKIP_JWT_VALIDATION=true` to disable authentication for local development.
This allows requests without a Bearer token.

## Endpoints

After deployment, the following endpoints are available:

### Marketplace Handler Service

| Endpoint | Description |
|----------|-------------|
| `GET /health` | Health check |
| `GET /ready` | Readiness check |
| `POST /dcr` | Hybrid endpoint (Pub/Sub events + DCR requests) |
| `POST /oauth/register` | DCR endpoint (RFC 7591 compliant path) |

### Insights Agent Service

| Endpoint | Description |
|----------|-------------|
| `GET /health` | Health check |
| `GET /ready` | Readiness check |
| `GET /.well-known/agent.json` | A2A AgentCard (public) |
| `POST /` | A2A JSON-RPC endpoint (message/send, message/stream) |
| `GET /usage` | Aggregate usage statistics |
| `GET /oauth/callback` | OAuth callback from Red Hat SSO |

## Testing the Deployment

```bash
# Get service URLs
HANDLER_URL=$(gcloud run services describe marketplace-handler \
  --region=$GOOGLE_CLOUD_LOCATION \
  --project=$GOOGLE_CLOUD_PROJECT \
  --format='value(status.url)')

AGENT_URL=$(gcloud run services describe insights-agent \
  --region=$GOOGLE_CLOUD_LOCATION \
  --project=$GOOGLE_CLOUD_PROJECT \
  --format='value(status.url)')

# Test marketplace handler health
curl $HANDLER_URL/health

# Test agent health
curl $AGENT_URL/health

# Get AgentCard (public endpoint)
curl $AGENT_URL/.well-known/agent.json

# View logs for each service
gcloud run logs read marketplace-handler \
  --region=$GOOGLE_CLOUD_LOCATION \
  --project=$GOOGLE_CLOUD_PROJECT

gcloud run logs read insights-agent \
  --region=$GOOGLE_CLOUD_LOCATION \
  --project=$GOOGLE_CLOUD_PROJECT
```

## Database Architecture

Cloud Run deployments **require PostgreSQL** (Cloud SQL) for production. The system uses **two databases** for security isolation:

| Database | Purpose | Service |
|----------|---------|---------|
| Marketplace DB | Orders, entitlements, DCR clients | Both handler and agent |
| Session DB | ADK agent sessions | Agent only |

This separation ensures:
- Agent sessions cannot access marketplace/auth data
- Compromised agents cannot access DCR credentials
- Different retention policies can be applied

> **Setup:** See [Step 3. Set Up Cloud SQL Database](#3-set-up-cloud-sql-database) in Quick Start.

### Adding Cloud SQL to Existing Services

If you deployed services before setting up Cloud SQL, add the connection:

```bash
CONNECTION_NAME=$(gcloud sql instances describe insights-agent-db \
  --project=$GOOGLE_CLOUD_PROJECT --format='value(connectionName)')

# Add to marketplace handler
gcloud run services update marketplace-handler \
  --add-cloudsql-instances=$CONNECTION_NAME \
  --region=$GOOGLE_CLOUD_LOCATION \
  --project=$GOOGLE_CLOUD_PROJECT

# Add to insights agent
gcloud run services update insights-agent \
  --add-cloudsql-instances=$CONNECTION_NAME \
  --region=$GOOGLE_CLOUD_LOCATION \
  --project=$GOOGLE_CLOUD_PROJECT
```

### Session Database Behavior

- If `SESSION_DATABASE_URL` is set: Uses PostgreSQL for session persistence
- If `SESSION_DATABASE_URL` is not set: Uses in-memory storage (sessions lost on restart)

For production, always configure `SESSION_DATABASE_URL` to ensure session persistence across container restarts and scaling events.

## CI/CD with Cloud Build

The `cloudbuild.yaml` file provides automated builds:

1. **On push to main**: Trigger automatic deployments
2. **On pull request**: Build and test only

Set up a Cloud Build trigger:

```bash
gcloud builds triggers create github \
  --repo-name=insights-agent \
  --repo-owner=your-org \
  --branch-pattern='^main$' \
  --build-config=cloudbuild.yaml \
  --project=$GOOGLE_CLOUD_PROJECT
```

## Custom Domain

Map a custom domain to your Cloud Run service:

```bash
gcloud run domain-mappings create \
  --service=insights-agent \
  --domain=agent.yourdomain.com \
  --region=$GOOGLE_CLOUD_LOCATION \
  --project=$GOOGLE_CLOUD_PROJECT
```

Follow the instructions to verify domain ownership and configure DNS.

## Testing the Agent

Once deployed, you can test the agent using a local proxy that handles Google Cloud Run authentication.

### Test Agent Card

Verify the agent is running and accessible:

```bash
# Get the agent URL
AGENT_URL=$(gcloud run services describe insights-agent \
  --region=$GOOGLE_CLOUD_LOCATION \
  --project=$GOOGLE_CLOUD_PROJECT \
  --format='value(status.url)')

# Test agent card endpoint (requires authentication)
curl -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
  $AGENT_URL/.well-known/agent.json | jq .
```

### Test A2A Requests with Local Proxy

The local proxy handles Google Cloud Run authentication, allowing you to test with just your Red Hat SSO token.

**1. Start the local proxy:**

```bash
# Start proxy on localhost:8080
gcloud run services proxy insights-agent \
  --region=$GOOGLE_CLOUD_LOCATION \
  --project=$GOOGLE_CLOUD_PROJECT \
  --port=8080
```

This command will keep running in your terminal. The proxy authenticates all requests to Cloud Run using your current `gcloud` credentials.

**2. Get a Red Hat SSO access token:**

In a new terminal, use one of these methods:

**Option A: Using `ocm` CLI (Easiest)**

If you have the [ocm CLI](https://github.com/openshift-online/ocm-cli) installed:

```bash
# Login to OCM (if not already logged in)
ocm login

# Get access token
export RED_HAT_TOKEN=$(ocm token)

# Verify token is valid
echo $RED_HAT_TOKEN | cut -d. -f2 | base64 -d 2>/dev/null | jq .
```

**Option B: Using OAuth Flow**

Initiate the OAuth flow through the agent:

```bash
# Start OAuth flow (open this URL in your browser)
echo "http://localhost:8080/oauth/authorize?state=test123"
```

After logging in to Red Hat SSO, you'll be redirected to a callback URL with a code parameter. Extract the code and exchange it for tokens:

```bash
# Exchange authorization code for access token
curl -X POST http://localhost:8080/oauth/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=authorization_code" \
  -d "code=YOUR_AUTHORIZATION_CODE" \
  -d "redirect_uri=http://localhost:8080/oauth/callback"
```

Save the `access_token` from the response:

```bash
export RED_HAT_TOKEN="eyJhbGciOiJSUzI1NiIsInR5cCI..."
```

**3. Test the A2A endpoint:**

```bash
# Send a test message to the agent
curl -X POST http://localhost:8080/ \
  -H "Authorization: Bearer $RED_HAT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [
      {
        "role": "user",
        "parts": [{"text": "What are the latest CVEs affecting my systems?"}]
      }
    ]
  }' | jq .
```

**4. Test other endpoints:**

```bash
# Get user information
curl http://localhost:8080/oauth/userinfo \
  -H "Authorization: Bearer $RED_HAT_TOKEN" | jq .

# Check health endpoint (no auth required)
curl http://localhost:8080/health | jq .

# Get usage statistics
curl http://localhost:8080/usage | jq .
```

### Cleanup After Testing

When you're done testing, clean up the local proxy:

**1. Stop the proxy:**

Press `Ctrl+C` in the terminal where the proxy is running.

**2. Clean up port (if needed):**

If the port is still in use:

```bash
# Find and kill process using port 8080
lsof -ti:8080 | xargs kill -9

# Or on systems without lsof
fuser -k 8080/tcp
```

**Note:** The proxy doesn't create any cloud resources - it only runs locally on your machine. Stopping the proxy (Ctrl+C) is sufficient to clean up.

### Testing Without Proxy (Direct Cloud Run Access)

If you prefer to test without the proxy, you'll need to:

1. **Allow unauthenticated access** (requires admin permissions):
   ```bash
   gcloud run services add-iam-policy-binding insights-agent \
     --region=$GOOGLE_CLOUD_LOCATION \
     --project=$GOOGLE_CLOUD_PROJECT \
     --member="allUsers" \
     --role="roles/run.invoker"
   ```

2. **Test directly** with the Cloud Run URL:
   ```bash
   # Get Red Hat SSO token (using ocm or OAuth flow)
   export RED_HAT_TOKEN=$(ocm token)

   curl -X POST $AGENT_URL/ \
     -H "Authorization: Bearer $RED_HAT_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"messages": [{"role": "user", "parts": [{"text": "Hello"}]}]}'
   ```

**Security Note:** Allowing unauthenticated access makes the service publicly accessible. Only use this for development/testing environments, not production.

## Monitoring

View metrics in Google Cloud Console:
- **Cloud Run** → **Services** → **insights-agent** → **Metrics**

Set up alerts:
```bash
gcloud monitoring policies create \
  --display-name="Insights Agent Error Rate" \
  --condition-display-name="Error rate > 5%" \
  --condition-filter='resource.type="cloud_run_revision" AND metric.type="run.googleapis.com/request_count" AND metric.labels.response_code_class="5xx"' \
  --project=$GOOGLE_CLOUD_PROJECT
```

## Troubleshooting

### View Logs

```bash
gcloud run logs read insights-agent \
  --region=$GOOGLE_CLOUD_LOCATION \
  --project=$GOOGLE_CLOUD_PROJECT \
  --limit=100
```

### Check Service Status

```bash
gcloud run services describe insights-agent \
  --region=$GOOGLE_CLOUD_LOCATION \
  --project=$GOOGLE_CLOUD_PROJECT
```

### Common Issues

1. **Secret access denied**: Ensure service account has `secretmanager.secretAccessor` role
2. **Container fails to start**: Check logs for missing environment variables
3. **Database connection timeout**: Ensure Cloud SQL connection is configured

## Cleanup / Teardown

To remove all resources created by the setup and deploy scripts:

```bash
./deploy/cloudrun/cleanup.sh
```

This will delete:
- Cloud Run service
- Pub/Sub topic and subscription
- Secret Manager secrets
- Service account and IAM bindings

Use `--force` to skip the confirmation prompt:

```bash
./deploy/cloudrun/cleanup.sh --force
```

**Note**: The cleanup script does NOT delete container images in GCR, Cloud SQL instances, or VPC connectors. Delete these separately if needed:

```bash
# Delete container images
gcloud container images delete gcr.io/$GOOGLE_CLOUD_PROJECT/insights-agent --force-delete-tags --quiet
gcloud container images delete gcr.io/$GOOGLE_CLOUD_PROJECT/insights-mcp --force-delete-tags --quiet

# Delete Cloud SQL instance (if created)
gcloud sql instances delete INSTANCE_NAME --project=$GOOGLE_CLOUD_PROJECT

# Delete VPC connector (if created)
gcloud compute networks vpc-access connectors delete CONNECTOR_NAME --region=$GOOGLE_CLOUD_LOCATION --project=$GOOGLE_CLOUD_PROJECT
```
