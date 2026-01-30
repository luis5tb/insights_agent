#!/bin/bash
# =============================================================================
# Google Cloud Run Deployment Cleanup Script
# =============================================================================
#
# This script removes all GCP resources created by setup.sh and deploy.sh:
# - Cloud Run service
# - Pub/Sub topic and subscription
# - Secrets in Secret Manager
# - Service account and IAM bindings
#
# Usage:
#   ./deploy/cloudrun/cleanup.sh [--force]
#
# Options:
#   --force    Skip confirmation prompt
#
# Prerequisites:
#   - gcloud CLI installed and authenticated
#   - GOOGLE_CLOUD_PROJECT environment variable set
#
# =============================================================================

set -euo pipefail

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# =============================================================================
# Configuration
# =============================================================================

PROJECT_ID="${GOOGLE_CLOUD_PROJECT:-}"
REGION="${GOOGLE_CLOUD_LOCATION:-us-central1}"
SERVICE_NAME="${SERVICE_NAME:-insights-agent}"
SERVICE_ACCOUNT="${SERVICE_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

# Parse arguments
FORCE=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --force)
            FORCE=true
            shift
            ;;
        *)
            log_error "Unknown option: $1"
            echo "Usage: $0 [--force]"
            exit 1
            ;;
    esac
done

# Validate required variables
if [[ -z "$PROJECT_ID" ]]; then
    log_error "GOOGLE_CLOUD_PROJECT environment variable is required"
    echo "  export GOOGLE_CLOUD_PROJECT=your-project-id"
    exit 1
fi

log_warn "This will delete the following resources from project: $PROJECT_ID"
echo ""
echo "  - Cloud Run service: $SERVICE_NAME"
echo "  - Pub/Sub topic: marketplace-entitlements"
echo "  - Pub/Sub subscription: marketplace-entitlements-sub"
echo "  - Secrets: google-api-key, lightspeed-client-id, lightspeed-client-secret,"
echo "             redhat-sso-client-id, redhat-sso-client-secret, database-url, redis-url"
echo "  - Service account: $SERVICE_ACCOUNT"
echo ""

# Confirmation prompt
if [[ "$FORCE" != "true" ]]; then
    read -p "Are you sure you want to delete these resources? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        log_info "Cleanup cancelled"
        exit 0
    fi
fi

echo ""
log_info "Starting cleanup..."

# =============================================================================
# Step 1: Delete Cloud Run Service
# =============================================================================
log_info "Deleting Cloud Run service..."

if gcloud run services describe "$SERVICE_NAME" --region="$REGION" --project="$PROJECT_ID" &>/dev/null; then
    gcloud run services delete "$SERVICE_NAME" \
        --region="$REGION" \
        --project="$PROJECT_ID" \
        --quiet
    log_info "Cloud Run service '$SERVICE_NAME' deleted"
else
    log_info "Cloud Run service '$SERVICE_NAME' does not exist, skipping"
fi

# =============================================================================
# Step 2: Delete Pub/Sub Resources
# =============================================================================
log_info "Deleting Pub/Sub resources..."

PUBSUB_TOPIC="marketplace-entitlements"
PUBSUB_SUBSCRIPTION="${PUBSUB_TOPIC}-sub"

# Delete subscription first (must be deleted before topic)
if gcloud pubsub subscriptions describe "$PUBSUB_SUBSCRIPTION" --project="$PROJECT_ID" &>/dev/null; then
    gcloud pubsub subscriptions delete "$PUBSUB_SUBSCRIPTION" \
        --project="$PROJECT_ID" \
        --quiet
    log_info "Pub/Sub subscription '$PUBSUB_SUBSCRIPTION' deleted"
else
    log_info "Pub/Sub subscription '$PUBSUB_SUBSCRIPTION' does not exist, skipping"
fi

# Delete topic
if gcloud pubsub topics describe "$PUBSUB_TOPIC" --project="$PROJECT_ID" &>/dev/null; then
    gcloud pubsub topics delete "$PUBSUB_TOPIC" \
        --project="$PROJECT_ID" \
        --quiet
    log_info "Pub/Sub topic '$PUBSUB_TOPIC' deleted"
else
    log_info "Pub/Sub topic '$PUBSUB_TOPIC' does not exist, skipping"
fi

# =============================================================================
# Step 3: Delete Secrets
# =============================================================================
log_info "Deleting secrets from Secret Manager..."

secrets=(
    "google-api-key"
    "lightspeed-client-id"
    "lightspeed-client-secret"
    "redhat-sso-client-id"
    "redhat-sso-client-secret"
    "database-url"
    "redis-url"
)

for secret in "${secrets[@]}"; do
    if gcloud secrets describe "$secret" --project="$PROJECT_ID" &>/dev/null; then
        gcloud secrets delete "$secret" \
            --project="$PROJECT_ID" \
            --quiet
        log_info "  Secret '$secret' deleted"
    else
        log_info "  Secret '$secret' does not exist, skipping"
    fi
done

# =============================================================================
# Step 4: Remove IAM Bindings and Delete Service Account
# =============================================================================
log_info "Removing service account IAM bindings..."

roles=(
    "roles/run.invoker"
    "roles/secretmanager.secretAccessor"
    "roles/aiplatform.user"
    "roles/cloudsql.client"
    "roles/redis.editor"
    "roles/pubsub.subscriber"
    "roles/pubsub.publisher"
    "roles/servicecontrol.serviceController"
    "roles/logging.logWriter"
    "roles/monitoring.metricWriter"
)

if gcloud iam service-accounts describe "$SERVICE_ACCOUNT" --project="$PROJECT_ID" &>/dev/null; then
    for role in "${roles[@]}"; do
        log_info "  Removing $role..."
        gcloud projects remove-iam-policy-binding "$PROJECT_ID" \
            --member="serviceAccount:$SERVICE_ACCOUNT" \
            --role="$role" \
            --quiet 2>/dev/null || true
    done

    log_info "Deleting service account..."
    gcloud iam service-accounts delete "$SERVICE_ACCOUNT" \
        --project="$PROJECT_ID" \
        --quiet
    log_info "Service account '$SERVICE_ACCOUNT' deleted"
else
    log_info "Service account '$SERVICE_ACCOUNT' does not exist, skipping"
fi

# =============================================================================
# Summary
# =============================================================================
echo ""
log_info "=========================================="
log_info "Cleanup complete!"
log_info "=========================================="
echo ""
echo "The following resources have been removed:"
echo "  - Cloud Run service"
echo "  - Pub/Sub topic and subscription"
echo "  - Secret Manager secrets"
echo "  - Service account and IAM bindings"
echo ""
echo "Note: The following resources were NOT deleted (if created manually):"
echo "  - Cloud SQL instances"
echo "  - Memorystore (Redis) instances"
echo "  - VPC connectors"
echo "  - Cloud Build triggers"
echo ""
echo "To delete these, use the respective gcloud commands:"
echo "  gcloud sql instances delete INSTANCE_NAME --project=$PROJECT_ID"
echo "  gcloud redis instances delete INSTANCE_NAME --region=$REGION --project=$PROJECT_ID"
echo "  gcloud compute networks vpc-access connectors delete CONNECTOR_NAME --region=$REGION --project=$PROJECT_ID"
echo ""
