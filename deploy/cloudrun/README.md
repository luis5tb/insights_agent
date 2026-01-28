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
```

### 2. Run Setup Script

The setup script enables required APIs, creates a service account, and sets up secrets:

```bash
./deploy/cloudrun/setup.sh
```

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

# Database URL (Cloud SQL)
echo -n 'postgresql+asyncpg://user:pass@/dbname?host=/cloudsql/PROJECT:REGION:INSTANCE' | \
  gcloud secrets versions add database-url --data-file=- --project=$GOOGLE_CLOUD_PROJECT

# Redis URL (Memorystore)
echo -n 'redis://10.0.0.1:6379/0' | \
  gcloud secrets versions add redis-url --data-file=- --project=$GOOGLE_CLOUD_PROJECT
```

### 4. Deploy

```bash
./deploy/cloudrun/deploy.sh
```

Or use the ADK CLI directly:

```bash
adk deploy cloud_run \
  --project=$GOOGLE_CLOUD_PROJECT \
  --region=$GOOGLE_CLOUD_LOCATION \
  --service_name=$SERVICE_NAME \
  .
```

## Deployment Options

### Using ADK CLI (Recommended)

```bash
adk deploy cloud_run \
  --project=$GOOGLE_CLOUD_PROJECT \
  --region=$GOOGLE_CLOUD_LOCATION \
  --service_name=insights-agent \
  --with_ui \
  .
```

### Using gcloud CLI

```bash
gcloud run deploy insights-agent \
  --source . \
  --region $GOOGLE_CLOUD_LOCATION \
  --project $GOOGLE_CLOUD_PROJECT \
  --allow-unauthenticated
```

### Using Cloud Build

```bash
gcloud builds submit \
  --config=cloudbuild.yaml \
  --project=$GOOGLE_CLOUD_PROJECT \
  --substitutions=_SERVICE_NAME=insights-agent,_REGION=us-central1
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

## Endpoints

After deployment, the following endpoints are available:

| Endpoint | Description |
|----------|-------------|
| `GET /health` | Health check |
| `GET /ready` | Readiness check |
| `GET /.well-known/agent.json` | A2A AgentCard |
| `POST /a2a` | A2A message endpoint |
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

### Cloud SQL (PostgreSQL)

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

### Memorystore (Redis)

1. Create Memorystore instance:
   ```bash
   gcloud redis instances create insights-agent-redis \
     --size=1 \
     --region=$GOOGLE_CLOUD_LOCATION \
     --project=$GOOGLE_CLOUD_PROJECT
   ```

2. Get the Redis IP:
   ```bash
   REDIS_HOST=$(gcloud redis instances describe insights-agent-redis \
     --region=$GOOGLE_CLOUD_LOCATION \
     --project=$GOOGLE_CLOUD_PROJECT \
     --format='value(host)')
   ```

3. Update REDIS_URL secret:
   ```bash
   echo -n "redis://$REDIS_HOST:6379/0" | \
     gcloud secrets versions add redis-url --data-file=- --project=$GOOGLE_CLOUD_PROJECT
   ```

4. Configure VPC connector for Cloud Run to access Memorystore.

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
4. **Redis connection failed**: Ensure VPC connector is configured for Memorystore
