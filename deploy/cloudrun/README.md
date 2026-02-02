# Google Cloud Run Deployment

Deploy the Red Hat Insights Agent to Google Cloud Run for production use.

## Architecture

The deployment includes two containers running as sidecars:

```
┌─────────────────────────────────────────────────────────────┐
│                    Cloud Run Service                         │
│  ┌─────────────────────┐      ┌─────────────────────────┐  │
│  │   Insights Agent    │ HTTP │   Insights MCP Server   │  │
│  │   (Port 8000)       │◄────►│   (Port 8080)           │  │
│  │                     │      │                         │  │
│  │   - Gemini 2.5      │      │   - Advisor tools       │  │
│  │   - A2A protocol    │      │   - Inventory tools     │  │
│  │   - OAuth 2.0       │      │   - Vulnerability tools │  │
│  └─────────────────────┘      └───────────┬─────────────┘  │
│                                           │                 │
└───────────────────────────────────────────┼─────────────────┘
                                            │
                                            ▼
                                   ┌─────────────────┐
                                   │console.redhat.com│
                                   │ (Insights APIs) │
                                   └─────────────────┘
```

The MCP server authenticates with console.redhat.com using Lightspeed service account credentials stored in Secret Manager.

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

### 3. Configure Secrets

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

# Database URL (Cloud SQL) - OPTIONAL, not currently used
# The agent currently uses in-memory storage. This is for future use.
# echo -n 'postgresql+asyncpg://user:pass@/dbname?host=/cloudsql/PROJECT:REGION:INSTANCE' | \
#   gcloud secrets versions add database-url --data-file=- --project=$GOOGLE_CLOUD_PROJECT
```

### 4. Deploy

The deploy script supports multiple deployment methods. The default (`yaml`) is recommended
as it includes the MCP sidecar container.

```bash
# Build and deploy (recommended for first deployment)
./deploy/cloudrun/deploy.sh --build

# Deploy with existing image
./deploy/cloudrun/deploy.sh --image gcr.io/my-project/insights-agent:v1.0
```

**Deploy script options:**

| Flag | Description |
|------|-------------|
| `--method <method>` | Deployment method: `yaml` (default), `adk`, `cloudbuild` |
| `--image <image>` | Container image for the agent (default: `gcr.io/$PROJECT_ID/insights-agent:latest`) |
| `--mcp-image <image>` | Container image for the MCP server (default: `ghcr.io/redhatinsights/red-hat-lightspeed-mcp:latest`) |
| `--build` | Build the agent image before deploying |
| `--with-ui` | Include the ADK web UI (only for `adk` method) |
| `--allow-unauthenticated` | Allow public access without Cloud Run IAM authentication |

**Deployment methods:**

| Method | MCP Sidecar | Description |
|--------|-------------|-------------|
| `yaml` | ✅ Yes | Uses `service.yaml` with variable substitution (recommended) |
| `adk` | ❌ No | Uses ADK CLI (does not support sidecars) |
| `cloudbuild` | ✅ Yes | Uses Cloud Build with `cloudbuild.yaml` |

**Examples:**

```bash
# Deploy using service.yaml (default, includes MCP sidecar)
./deploy/cloudrun/deploy.sh --build

# Deploy with custom image registry
./deploy/cloudrun/deploy.sh --image quay.io/myorg/insights-agent:latest

# Deploy with ADK CLI (no MCP sidecar - not recommended for production)
./deploy/cloudrun/deploy.sh --method adk --with-ui

# Deploy using Cloud Build
./deploy/cloudrun/deploy.sh --method cloudbuild
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
  --substitutions=_SERVICE_NAME=insights-agent,_REGION=us-central1,_MCP_IMAGE=ghcr.io/redhatinsights/red-hat-lightspeed-mcp:latest
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
| Image | ghcr.io/redhatinsights/red-hat-lightspeed-mcp:latest | MCP server image |

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

| Endpoint | Description |
|----------|-------------|
| `GET /health` | Health check |
| `GET /ready` | Readiness check |
| `GET /.well-known/agent.json` | A2A AgentCard |
| `POST /` | A2A JSON-RPC endpoint (message/send, message/stream) |
| `GET /usage` | Aggregate usage statistics |
| `GET /oauth/authorize` | OAuth authorization |
| `GET /oauth/callback` | OAuth callback |
| `POST /oauth/token` | OAuth token endpoint |

## Testing the Deployment

```bash
# Get service URL
SERVICE_URL=$(gcloud run services describe insights-agent \
  --region=$GOOGLE_CLOUD_LOCATION \
  --project=$GOOGLE_CLOUD_PROJECT \
  --format='value(status.url)')

# Test health endpoint
curl $SERVICE_URL/health

# Get AgentCard
curl $SERVICE_URL/.well-known/agent.json

# View logs
gcloud run logs read insights-agent \
  --region=$GOOGLE_CLOUD_LOCATION \
  --project=$GOOGLE_CLOUD_PROJECT
```

## Database Options

> **Note**: The current implementation uses **in-memory storage** for all state
> (sessions, tasks, marketplace entitlements, registered clients). This means
> data is lost when the service restarts. The `database-url` secret is created
> but not currently used. Database persistence is planned for a future release.

### Cloud SQL (PostgreSQL) - Future Use

When database persistence is implemented, you'll need Cloud SQL:

1. Create Cloud SQL instance:
   ```bash
   gcloud sql instances create insights-agent-db \
     --database-version=POSTGRES_16 \
     --tier=db-f1-micro \
     --region=$GOOGLE_CLOUD_LOCATION \
     --project=$GOOGLE_CLOUD_PROJECT
   ```

2. Create database and user:
   ```bash
   gcloud sql databases create insights_agent \
     --instance=insights-agent-db \
     --project=$GOOGLE_CLOUD_PROJECT

   gcloud sql users create insights \
     --instance=insights-agent-db \
     --password=YOUR_PASSWORD \
     --project=$GOOGLE_CLOUD_PROJECT
   ```

3. Update DATABASE_URL secret:
   ```bash
   CONNECTION_NAME=$(gcloud sql instances describe insights-agent-db \
     --project=$GOOGLE_CLOUD_PROJECT --format='value(connectionName)')

   echo -n "postgresql+asyncpg://insights:YOUR_PASSWORD@/insights_agent?host=/cloudsql/$CONNECTION_NAME" | \
     gcloud secrets versions add database-url --data-file=- --project=$GOOGLE_CLOUD_PROJECT
   ```

4. Add Cloud SQL connection to Cloud Run:
   ```bash
   gcloud run services update insights-agent \
     --add-cloudsql-instances=$CONNECTION_NAME \
     --region=$GOOGLE_CLOUD_LOCATION \
     --project=$GOOGLE_CLOUD_PROJECT
   ```

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

**Note**: The cleanup script does NOT delete Cloud SQL instances or VPC connectors that may have been created manually. Delete these separately if needed:

```bash
gcloud sql instances delete INSTANCE_NAME --project=$GOOGLE_CLOUD_PROJECT
gcloud compute networks vpc-access connectors delete CONNECTOR_NAME --region=$GOOGLE_CLOUD_LOCATION --project=$GOOGLE_CLOUD_PROJECT
```
