#!/bin/bash
# =============================================================================
# Google Cloud Run Deployment Script
# =============================================================================
#
# Deploys the Insights Agent to Google Cloud Run
#
# Usage:
#   ./deploy/cloudrun/deploy.sh [--with-ui] [--allow-unauthenticated]
#
# Prerequisites:
#   - Run setup.sh first to configure GCP services
#   - Update secrets in Secret Manager with actual values
#
# =============================================================================

set -euo pipefail

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# =============================================================================
# Configuration
# =============================================================================

PROJECT_ID="${GOOGLE_CLOUD_PROJECT:-}"
REGION="${GOOGLE_CLOUD_LOCATION:-us-central1}"
SERVICE_NAME="${SERVICE_NAME:-insights-agent}"
IMAGE_TAG="${IMAGE_TAG:-latest}"

# Parse arguments
WITH_UI=false
ALLOW_UNAUTH=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --with-ui)
            WITH_UI=true
            shift
            ;;
        --allow-unauthenticated)
            ALLOW_UNAUTH=true
            shift
            ;;
        *)
            log_error "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Validate required variables
if [[ -z "$PROJECT_ID" ]]; then
    log_error "GOOGLE_CLOUD_PROJECT environment variable is required"
    exit 1
fi

log_info "Deploying Insights Agent to Cloud Run"
log_info "  Project: $PROJECT_ID"
log_info "  Region: $REGION"
log_info "  Service: $SERVICE_NAME"

# =============================================================================
# Option 1: Deploy using ADK CLI (recommended)
# =============================================================================
deploy_with_adk() {
    log_info "Deploying with ADK CLI..."

    local cmd="adk deploy cloud_run \
        --project=$PROJECT_ID \
        --region=$REGION \
        --service_name=$SERVICE_NAME \
        --port=8000"

    if [[ "$WITH_UI" == "true" ]]; then
        cmd="$cmd --with_ui"
    fi

    # ADK expects the agent directory
    $cmd .
}

# =============================================================================
# Option 2: Deploy using gcloud CLI
# =============================================================================
deploy_with_gcloud() {
    log_info "Deploying with gcloud CLI..."

    # Build arguments
    local auth_flag=""
    if [[ "$ALLOW_UNAUTH" == "true" ]]; then
        auth_flag="--allow-unauthenticated"
    else
        auth_flag="--no-allow-unauthenticated"
    fi

    # Deploy from source
    gcloud run deploy "$SERVICE_NAME" \
        --source . \
        --region "$REGION" \
        --project "$PROJECT_ID" \
        --platform managed \
        --port 8000 \
        --cpu 2 \
        --memory 2Gi \
        --min-instances 0 \
        --max-instances 10 \
        --timeout 300 \
        --concurrency 80 \
        --service-account "insights-agent@${PROJECT_ID}.iam.gserviceaccount.com" \
        --set-env-vars "GOOGLE_GENAI_USE_VERTEXAI=TRUE,GOOGLE_CLOUD_PROJECT=${PROJECT_ID},GOOGLE_CLOUD_LOCATION=${REGION},AGENT_HOST=0.0.0.0,AGENT_PORT=8000,LOG_FORMAT=json" \
        --set-secrets "GOOGLE_API_KEY=google-api-key:latest,LIGHTSPEED_CLIENT_ID=lightspeed-client-id:latest,LIGHTSPEED_CLIENT_SECRET=lightspeed-client-secret:latest,RED_HAT_SSO_CLIENT_ID=redhat-sso-client-id:latest,RED_HAT_SSO_CLIENT_SECRET=redhat-sso-client-secret:latest,REDIS_URL=redis-url:latest,DATABASE_URL=database-url:latest" \
        $auth_flag
}

# =============================================================================
# Option 3: Deploy using Cloud Build
# =============================================================================
deploy_with_cloudbuild() {
    log_info "Deploying with Cloud Build..."

    gcloud builds submit \
        --config=cloudbuild.yaml \
        --project="$PROJECT_ID" \
        --substitutions="_SERVICE_NAME=${SERVICE_NAME},_REGION=${REGION},_IMAGE_TAG=${IMAGE_TAG}"
}

# =============================================================================
# Main deployment
# =============================================================================

# Check if ADK is available
if command -v adk &>/dev/null; then
    deploy_with_adk
else
    log_info "ADK CLI not found, using gcloud CLI"
    deploy_with_gcloud
fi

# =============================================================================
# Post-deployment
# =============================================================================

log_info "Deployment complete!"
echo ""

# Get service URL
SERVICE_URL=$(gcloud run services describe "$SERVICE_NAME" \
    --region="$REGION" \
    --project="$PROJECT_ID" \
    --format='value(status.url)' 2>/dev/null || echo "")

if [[ -n "$SERVICE_URL" ]]; then
    log_info "Service URL: $SERVICE_URL"
    echo ""
    echo "Test the deployment:"
    echo "  curl $SERVICE_URL/health"
    echo "  curl $SERVICE_URL/.well-known/agent.json"
    echo ""
    echo "View logs:"
    echo "  gcloud run logs read $SERVICE_NAME --region=$REGION --project=$PROJECT_ID"
else
    log_warn "Could not retrieve service URL. Check deployment status with:"
    echo "  gcloud run services describe $SERVICE_NAME --region=$REGION --project=$PROJECT_ID"
fi
