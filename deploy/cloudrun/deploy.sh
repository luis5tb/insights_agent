#!/bin/bash
# =============================================================================
# Google Cloud Run Deployment Script
# =============================================================================
#
# Deploys the Insights Agent to Google Cloud Run with MCP sidecar
#
# Usage:
#   ./deploy/cloudrun/deploy.sh [OPTIONS]
#
# Options:
#   --method <method>     Deployment method: yaml, adk, cloudbuild
#                         (default: yaml)
#   --image <image>       Container image for the agent
#                         (default: gcr.io/$PROJECT_ID/insights-agent:latest)
#   --mcp-image <image>   Container image for the MCP server
#                         (default: quay.io/redhat-services-prod/insights-management-tenant/insights-mcp/red-hat-lightspeed-mcp:latest)
#   --with-ui             Include ADK web UI (only for adk method)
#   --allow-unauthenticated  Allow public access
#   --build               Build the agent image before deploying
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

# Default images
AGENT_IMAGE="${AGENT_IMAGE:-}"
# MCP image must be in GCR since Cloud Run doesn't support Quay.io directly
# See README.md for instructions to copy the image from Quay.io to GCR
MCP_IMAGE="${MCP_IMAGE:-gcr.io/${PROJECT_ID}/insights-mcp:latest}"

# Parse arguments
DEPLOY_METHOD="yaml"
WITH_UI=false
ALLOW_UNAUTH=false
BUILD_IMAGE=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --method)
            DEPLOY_METHOD="$2"
            shift 2
            ;;
        --image)
            AGENT_IMAGE="$2"
            shift 2
            ;;
        --mcp-image)
            MCP_IMAGE="$2"
            shift 2
            ;;
        --with-ui)
            WITH_UI=true
            shift
            ;;
        --allow-unauthenticated)
            ALLOW_UNAUTH=true
            shift
            ;;
        --build)
            BUILD_IMAGE=true
            shift
            ;;
        *)
            log_error "Unknown option: $1"
            echo "Usage: $0 [--method yaml|adk|cloudbuild] [--image IMAGE] [--mcp-image IMAGE] [--with-ui] [--allow-unauthenticated] [--build]"
            exit 1
            ;;
    esac
done

# Validate required variables
if [[ -z "$PROJECT_ID" ]]; then
    log_error "GOOGLE_CLOUD_PROJECT environment variable is required"
    exit 1
fi

# Set default agent image if not specified
if [[ -z "$AGENT_IMAGE" ]]; then
    AGENT_IMAGE="gcr.io/${PROJECT_ID}/insights-agent:${IMAGE_TAG}"
fi

log_info "Deploying Insights Agent to Cloud Run"
log_info "  Project: $PROJECT_ID"
log_info "  Region: $REGION"
log_info "  Service: $SERVICE_NAME"
log_info "  Method: $DEPLOY_METHOD"
log_info "  Agent Image: $AGENT_IMAGE"
log_info "  MCP Image: $MCP_IMAGE"

# =============================================================================
# Build image if requested
# =============================================================================
build_image() {
    log_info "Building agent image..."

    gcloud builds submit \
        --tag "$AGENT_IMAGE" \
        --project "$PROJECT_ID" \
        .

    log_info "Image built: $AGENT_IMAGE"
}

# =============================================================================
# Option 1: Deploy using service.yaml (recommended - includes MCP sidecar)
# =============================================================================
deploy_with_yaml() {
    log_info "Deploying with service.yaml..."

    # Create temporary file with substituted values
    local tmp_yaml
    tmp_yaml=$(mktemp)

    # Substitute variables in service.yaml
    sed -e "s|\${PROJECT_ID}|${PROJECT_ID}|g" \
        -e "s|\${REGION}|${REGION}|g" \
        -e "s|gcr.io/\${PROJECT_ID}/insights-agent:latest|${AGENT_IMAGE}|g" \
        -e "s|\${MCP_IMAGE}|${MCP_IMAGE}|g" \
        deploy/cloudrun/service.yaml > "$tmp_yaml"

    # Deploy using the YAML
    gcloud run services replace "$tmp_yaml" \
        --region "$REGION" \
        --project "$PROJECT_ID"

    # Set IAM policy if allowing unauthenticated
    if [[ "$ALLOW_UNAUTH" == "true" ]]; then
        log_info "Allowing unauthenticated access..."
        gcloud run services add-iam-policy-binding "$SERVICE_NAME" \
            --region "$REGION" \
            --project "$PROJECT_ID" \
            --member="allUsers" \
            --role="roles/run.invoker"
    fi

    # Cleanup
    rm -f "$tmp_yaml"
}

# =============================================================================
# Option 2: Deploy using ADK CLI
# =============================================================================
deploy_with_adk() {
    log_info "Deploying with ADK CLI..."
    log_warn "Note: ADK deploy does not support MCP sidecar. Use --method yaml or --method gcloud instead."

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

    log_warn "MCP sidecar was not deployed. The agent will not have access to Red Hat Insights tools."
    log_warn "To add MCP sidecar, run: ./deploy/cloudrun/deploy.sh --method yaml"
}

# =============================================================================
# Option 3: Deploy using Cloud Build
# =============================================================================
deploy_with_cloudbuild() {
    log_info "Deploying with Cloud Build..."

    gcloud builds submit \
        --config=cloudbuild.yaml \
        --project="$PROJECT_ID" \
        --substitutions="_SERVICE_NAME=${SERVICE_NAME},_REGION=${REGION},_IMAGE_TAG=${IMAGE_TAG},_MCP_IMAGE=${MCP_IMAGE}"
}

# =============================================================================
# Main deployment
# =============================================================================

# Build image if requested
if [[ "$BUILD_IMAGE" == "true" ]]; then
    build_image
fi

# Deploy based on method
case "$DEPLOY_METHOD" in
    yaml)
        deploy_with_yaml
        ;;
    adk)
        if command -v adk &>/dev/null; then
            deploy_with_adk
        else
            log_error "ADK CLI not found. Install it or use --method yaml"
            exit 1
        fi
        ;;
    cloudbuild)
        deploy_with_cloudbuild
        ;;
    *)
        log_error "Unknown deployment method: $DEPLOY_METHOD"
        echo "Valid methods: yaml, adk, cloudbuild"
        exit 1
        ;;
esac

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
