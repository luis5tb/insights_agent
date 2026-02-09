#!/usr/bin/env python3
"""Test client for the DCR (Dynamic Client Registration) endpoint.

Sends a signed software_statement JWT to the marketplace handler's /dcr
endpoint, simulating what Google Cloud Marketplace does when registering
a new OAuth client for a marketplace order.

The script uses the Google Cloud IAM Credentials API to sign the JWT with
a GCP service account you control.  This means the JWT is NOT signed by
Google's production cloud-agentspace service account, so the marketplace
handler must be running with SKIP_JWT_VALIDATION=true to accept it.

------------------------------------------------------------------------
Prerequisites
------------------------------------------------------------------------

1. A Google Cloud project with the IAM Credentials API enabled:
       gcloud services enable iamcredentials.googleapis.com

2. A GCP service account to sign JWTs.  You can create one:
       gcloud iam service-accounts create dcr-test \
           --display-name "DCR test signer"

   Grant yourself permission to sign JWTs on its behalf:
       gcloud iam service-accounts add-iam-policy-binding \
           dcr-test@<PROJECT>.iam.gserviceaccount.com \
           --member="user:<YOUR_EMAIL>" \
           --role="roles/iam.serviceAccountTokenCreator"

3. Python dependencies (install in a venv or with pip):
       pip install google-cloud-iam requests

4. Authenticate with Google Cloud:
       gcloud auth application-default login

------------------------------------------------------------------------
Marketplace handler configuration
------------------------------------------------------------------------

The handler must be started with at least these environment variables:

    # Skip Google JWT signature and issuer verification (required)
    SKIP_JWT_VALIDATION=true

    # --- Static credentials mode (no Keycloak needed) ---
    DCR_ENABLED=false
    RED_HAT_SSO_CLIENT_ID=my-test-client
    RED_HAT_SSO_CLIENT_SECRET=my-test-secret

    # --- OR: Real DCR against a local Keycloak ---
    # DCR_ENABLED=true
    # RED_HAT_SSO_ISSUER=http://localhost:8180/realms/test-realm
    # DCR_INITIAL_ACCESS_TOKEN=<your-keycloak-IAT>

    # Always required
    DCR_ENCRYPTION_KEY=<generate with: python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'>
    DATABASE_URL=sqlite+aiosqlite:///./insights_agent.db

    # Must match PROVIDER_URL below (or set AGENT_PROVIDER_URL on the handler)
    AGENT_PROVIDER_URL=https://your-agent-domain.com

------------------------------------------------------------------------
Local Keycloak setup (for real DCR testing)
------------------------------------------------------------------------

If you want to test the full DCR flow (real OAuth client creation in
Keycloak) without admin access to Red Hat SSO, you can run a local
Keycloak instance in Podman.  This is optional -- static credentials
mode (DCR_ENABLED=false) works without Keycloak.

1. Start Keycloak:

       podman run -d \
         --name keycloak-test \
         -p 8180:8080 \
         -e KC_BOOTSTRAP_ADMIN_USERNAME=admin \
         -e KC_BOOTSTRAP_ADMIN_PASSWORD=admin \
         quay.io/keycloak/keycloak:26.0 start-dev --http-port=8080

   Admin console: http://localhost:8180/admin  (admin / admin)

2. Get an admin token:

       ADMIN_TOKEN=$(curl -s -X POST \
         "http://localhost:8180/realms/master/protocol/openid-connect/token" \
         -d "client_id=admin-cli" \
         -d "username=admin" \
         -d "password=admin" \
         -d "grant_type=password" \
         | python -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

3. Create a test realm:

       curl -s -X POST "http://localhost:8180/admin/realms" \
         -H "Authorization: Bearer $ADMIN_TOKEN" \
         -H "Content-Type: application/json" \
         -d '{"realm": "test-realm", "enabled": true}'

4. Generate an Initial Access Token (IAT) for DCR:

       IAT=$(curl -s -X POST \
         "http://localhost:8180/admin/realms/test-realm/clients-initial-access" \
         -H "Authorization: Bearer $ADMIN_TOKEN" \
         -H "Content-Type: application/json" \
         -d '{"count": 100, "expiration": 86400}' \
         | python -c "import sys,json; print(json.load(sys.stdin)['token'])")
       echo "Initial Access Token: $IAT"

5. Configure the marketplace handler with:

       DCR_ENABLED=true
       SKIP_JWT_VALIDATION=true
       RED_HAT_SSO_ISSUER=http://localhost:8180/realms/test-realm
       DCR_INITIAL_ACCESS_TOKEN=<the IAT from step 4>

6. Run this script.  The handler will create a real OAuth client in
   your local Keycloak.  Verify at:
       http://localhost:8180/admin → test-realm → Clients

7. You can also test Keycloak DCR directly (without the handler):

       curl -s -X POST \
         "http://localhost:8180/realms/test-realm/clients-registrations/openid-connect" \
         -H "Authorization: Bearer $IAT" \
         -H "Content-Type: application/json" \
         -d '{
           "client_name": "gemini-order-test-123",
           "redirect_uris": ["http://localhost:8000/oauth/callback"],
           "grant_types": ["authorization_code", "refresh_token"],
           "token_endpoint_auth_method": "client_secret_basic",
           "application_type": "web"
         }'

8. Clean up:

       podman stop keycloak-test && podman rm keycloak-test

------------------------------------------------------------------------
Usage
------------------------------------------------------------------------

    # Minimal (uses defaults for everything except the service account)
    export TEST_SERVICE_ACCOUNT=dcr-test@my-project.iam.gserviceaccount.com
    python scripts/test_dcr.py

    # Override the handler URL and audience
    export MARKETPLACE_HANDLER_URL=http://localhost:8001
    export PROVIDER_URL=https://my-agent.example.com
    python scripts/test_dcr.py

    # Provide a specific order ID instead of a random one
    export TEST_ORDER_ID=order-abc-123
    python scripts/test_dcr.py

------------------------------------------------------------------------
Environment variables
------------------------------------------------------------------------

    TEST_SERVICE_ACCOUNT  (required)
        Email of the GCP service account used to sign the JWT.

    MARKETPLACE_HANDLER_URL  (default: http://localhost:8001)
        Base URL of the marketplace handler.

    PROVIDER_URL  (default: https://your-agent-domain.com)
        Expected audience (aud) claim.  Must match the handler's
        AGENT_PROVIDER_URL setting.

    TEST_ORDER_ID  (optional)
        Fixed marketplace order ID.  If unset a random UUID is generated.

    TEST_ACCOUNT_ID  (optional, default: test-procurement-account-001)
        Procurement account ID used as the JWT 'sub' claim.

    TEST_REDIRECT_URIS  (optional, default: https://gemini.google.com/callback)
        Comma-separated list of redirect URIs.
"""

from __future__ import annotations

import json
import os
import sys
import time
import uuid

import requests
from google.cloud import iam_credentials_v1

# ---------------------------------------------------------------------------
# Configuration from environment
# ---------------------------------------------------------------------------

HANDLER_URL = os.environ.get("MARKETPLACE_HANDLER_URL", "http://localhost:8001")
PROVIDER_URL = os.environ.get("PROVIDER_URL", "https://your-agent-domain.com")
TEST_SERVICE_ACCOUNT = os.environ.get("TEST_SERVICE_ACCOUNT")

CERT_BASE_URL = (
    "https://www.googleapis.com/service_accounts/v1/metadata/x509/"
)


def _require_service_account() -> str:
    if not TEST_SERVICE_ACCOUNT:
        print(
            "ERROR: TEST_SERVICE_ACCOUNT environment variable is required.\n"
            "Set it to the email of the GCP service account used to sign JWTs.\n"
            "Example:\n"
            "  export TEST_SERVICE_ACCOUNT=dcr-test@my-project.iam.gserviceaccount.com",
            file=sys.stderr,
        )
        sys.exit(1)
    return TEST_SERVICE_ACCOUNT


# ---------------------------------------------------------------------------
# JWT creation
# ---------------------------------------------------------------------------


def sign_jwt(service_account_email: str, payload: dict) -> str:
    """Sign a JWT using the GCP IAM Credentials API.

    Args:
        service_account_email: The service account to sign with.
        payload: JWT claims dict.

    Returns:
        The signed JWT string.
    """
    client = iam_credentials_v1.IAMCredentialsClient()
    name = f"projects/-/serviceAccounts/{service_account_email}"

    print(f"  Signing JWT with service account: {service_account_email}")
    response = client.sign_jwt(name=name, payload=json.dumps(payload))
    return response.signed_jwt


def build_software_statement(
    service_account_email: str,
    order_id: str,
    account_id: str,
    redirect_uris: list[str],
) -> str:
    """Build and sign a software_statement JWT.

    The claims mirror what Google Cloud Marketplace sends in production:
      - iss: certificate URL for the signing service account
      - aud: agent's provider URL
      - sub: procurement account ID
      - google.order: marketplace order ID
      - auth_app_redirect_uris: OAuth redirect URIs

    Args:
        service_account_email: GCP SA email for signing.
        order_id: Marketplace order ID.
        account_id: Procurement account ID.
        redirect_uris: OAuth redirect URIs.

    Returns:
        Signed JWT string.
    """
    now = int(time.time())

    payload = {
        "iss": CERT_BASE_URL + service_account_email,
        "iat": now,
        "exp": now + 3600,
        "aud": PROVIDER_URL,
        "sub": account_id,
        "auth_app_redirect_uris": redirect_uris,
        "google": {
            "order": order_id,
        },
    }

    print(f"  JWT claims:\n{json.dumps(payload, indent=4)}")
    return sign_jwt(service_account_email, payload)


# ---------------------------------------------------------------------------
# DCR request
# ---------------------------------------------------------------------------


def send_dcr_request(software_statement: str) -> None:
    """POST the software_statement to the /dcr endpoint.

    Args:
        software_statement: Signed JWT string.
    """
    url = f"{HANDLER_URL.rstrip('/')}/dcr"
    body = {"software_statement": software_statement}

    print(f"\n>>> POST {url}")
    response = requests.post(
        url,
        json=body,
        headers={"Content-Type": "application/json"},
        timeout=30,
    )

    print(f"<<< {response.status_code}")
    try:
        print(json.dumps(response.json(), indent=2))
    except Exception:
        print(response.text)

    if response.status_code == 201:
        print("\nDCR succeeded.")
    else:
        print("\nDCR failed.", file=sys.stderr)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    sa_email = _require_service_account()

    order_id = os.environ.get("TEST_ORDER_ID") or f"order-{uuid.uuid4()}"
    account_id = os.environ.get("TEST_ACCOUNT_ID", "test-procurement-account-001")
    redirect_uris = os.environ.get(
        "TEST_REDIRECT_URIS", "https://gemini.google.com/callback"
    ).split(",")

    print("=" * 60)
    print("DCR Test Client")
    print("=" * 60)
    print(f"  Handler URL : {HANDLER_URL}")
    print(f"  Provider URL: {PROVIDER_URL}")
    print(f"  Order ID    : {order_id}")
    print(f"  Account ID  : {account_id}")
    print(f"  Redirect URIs: {redirect_uris}")
    print()

    print("--- Building software_statement JWT ---")
    software_statement = build_software_statement(
        sa_email, order_id, account_id, redirect_uris
    )
    print(f"\n  JWT (first 80 chars): {software_statement[:80]}...")

    print("\n--- Sending DCR request ---")
    send_dcr_request(software_statement)

    # Send the same request again to test idempotency (should return
    # the same client_id/client_secret per Google's DCR spec)
    print("\n--- Sending duplicate DCR request (idempotency test) ---")
    send_dcr_request(software_statement)


if __name__ == "__main__":
    main()
