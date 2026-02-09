# Dynamic Client Registration (DCR) Architecture

## Overview

This document describes the architecture for Dynamic Client Registration (DCR) in the Insights Agent, enabling integration with Google Cloud Marketplace (Gemini Enterprise).

> **Note**: DCR is handled by the **Marketplace Handler** service, which is separate from the Insights Agent service. See [architecture.md](architecture.md) for the overall two-service architecture.

## Architecture Decision Records

### ADR-1: Real DCR with Red Hat SSO (Keycloak)

**Status**: Accepted

**Context**: Google Cloud Marketplace requires agents to implement DCR (RFC 7591) to create OAuth client credentials for each marketplace order. We need to decide between:
1. "Fake DCR" - Return tracking credentials without creating real OAuth clients
2. "Real DCR" - Create actual OAuth clients in Red Hat SSO via its DCR API

**Decision**: Implement **Real DCR** with Red Hat SSO (Keycloak).

**Rationale**:
- Aligns with Google's reference implementation (GE-A2A-Marketplace-Agent)
- Each order gets a real, functioning OAuth client
- Proper OAuth 2.0 flow with per-order isolation
- Better security and auditability

**Consequences**:
- Requires DCR to be enabled on Red Hat SSO realm
- Requires Initial Access Token from Red Hat SSO admin
- More complex setup but more robust architecture

---

### ADR-2: PostgreSQL for Persistence

**Status**: Accepted

**Context**: The current implementation uses in-memory dictionaries for storing:
- Marketplace accounts and entitlements
- DCR registered clients
- Usage tracking records

This data is lost on container restart.

**Decision**: Use **PostgreSQL** with SQLAlchemy async for all persistence.

**Rationale**:
- PostgreSQL already configured in podman deployment
- Supports async operations via asyncpg
- Enables horizontal scaling (multiple instances share state)
- Provides durability and auditability

**Consequences**:
- Adds SQLAlchemy and asyncpg dependencies
- Requires database migrations (Alembic)
- Slightly more complex deployment

---

### ADR-3: Configurable DCR Mode

**Status**: Accepted

**Context**: Not all deployments will have DCR enabled on Red Hat SSO, and development/testing environments may not need real DCR.

**Decision**: Make DCR mode configurable:
- `DCR_ENABLED=true` (default): Real DCR with Red Hat SSO
- `DCR_ENABLED=false`: Use static credentials from environment variables

**Rationale**:
- Enables production use with Gemini Enterprise (DCR enabled)
- Supports development/testing without DCR infrastructure
- Graceful fallback when DCR not available

**Consequences**:
- Two code paths to maintain
- Clear documentation needed for each mode

---

## System Architecture

The DCR flow is handled by the **Marketplace Handler** service (separate from the Agent):

```
                           Marketplace Handler Service (Port 8001)
┌─────────────────────────────────────────────────────────────────────────────────┐
│                                                                                  │
│  ┌──────────────┐                                                               │
│  │   Gemini     │                                                               │
│  │  Enterprise  │                                                               │
│  └──────┬───────┘                                                               │
│         │                                                                       │
│         │ POST /dcr                                                             │
│         │ {software_statement}                                                  │
│         ▼                                                                       │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │                      Hybrid /dcr Endpoint                                │   │
│  │                                                                          │   │
│  │  ┌─────────────┐     ┌──────────────────────────────────────────────┐   │   │
│  │  │ Route by    │     │  DCR Path (software_statement present)       │   │   │
│  │  │ Request     │────▶│                                              │   │   │
│  │  │ Content     │     │  1. Validate Google JWT signature            │   │   │
│  │  └─────────────┘     │  2. Extract order_id, redirect_uris          │   │   │
│  │                      │  3. Verify order exists in database          │   │   │
│  │                      │  4. Check for existing client for order      │   │   │
│  │                      │  5. Create client via Keycloak DCR           │   │   │
│  │                      │  6. Store client mapping in PostgreSQL       │   │   │
│  │                      │  7. Return {client_id, client_secret}        │   │   │
│  │                      └──────────────────────────────────────────────┘   │   │
│  │                                                                          │   │
│  │  ┌─────────────┐     ┌──────────────────────────────────────────────┐   │   │
│  │  │ Route by    │     │  Pub/Sub Path (message present)              │   │   │
│  │  │ Request     │────▶│                                              │   │   │
│  │  │ Content     │     │  1. Decode Pub/Sub message                   │   │   │
│  │  └─────────────┘     │  2. Extract event type                       │   │   │
│  │                      │  3. Call Google Procurement API (approve)    │   │   │
│  │                      │  4. Store account/entitlement in PostgreSQL  │   │   │
│  │                      │  5. Return success                           │   │   │
│  │                      └──────────────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────────────────────────┘   │
│                                                                                  │
│         │                               │                                       │
│         ▼                               ▼                                       │
│  ┌─────────────────┐           ┌─────────────────────────┐                     │
│  │   PostgreSQL    │           │    Red Hat SSO          │                     │
│  │  - accounts     │           │    (Keycloak)           │                     │
│  │  - entitlements │           │                         │                     │
│  │  - dcr_clients  │           │  POST /realms/{realm}/  │                     │
│  │  - usage        │           │  clients-registrations/ │                     │
│  └─────────────────┘           │  openid-connect         │                     │
│                                └─────────────────────────┘                     │
└─────────────────────────────────────────────────────────────────────────────────┘

                           Insights Agent Service (Port 8000)
┌─────────────────────────────────────────────────────────────────────────────────┐
│                                                                                  │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │                    AgentCard (/.well-known/agent.json)                   │   │
│  │                                                                          │   │
│  │  "capabilities": {                                                       │   │
│  │    "extensions": [{                                                      │   │
│  │      "uri": "urn:google:agent:dcr",                                      │   │
│  │      "params": {                                                         │   │
│  │        "endpoint": "https://marketplace-handler.../dcr"  ◀── Points to  │   │
│  │      }                                                       Handler     │   │
│  │    }]                                                                    │   │
│  │  }                                                                       │   │
│  └─────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## Configuration

### DCR Enabled (Production - Default)

```bash
# DCR Configuration
DCR_ENABLED=true
DCR_INITIAL_ACCESS_TOKEN="<token-from-keycloak-admin>"
DCR_CLIENT_NAME_PREFIX="gemini-order-"

# Red Hat SSO
RED_HAT_SSO_ISSUER="https://sso.redhat.com/auth/realms/redhat-external"

# Marketplace Database (shared for order validation)
DATABASE_URL="postgresql+asyncpg://insights:insights@marketplace-db:5432/marketplace"

# Session Database (isolated for agent sessions)
SESSION_DATABASE_URL="postgresql+asyncpg://agent:agent@session-db:5432/sessions"
```

### DCR Disabled (Development/Testing)

```bash
# DCR Configuration
DCR_ENABLED=false

# Static OAuth credentials (pre-registered)
RED_HAT_SSO_CLIENT_ID="my-dev-client"
RED_HAT_SSO_CLIENT_SECRET="my-dev-secret"

# Database (can use SQLite for dev - single database is fine)
DATABASE_URL="sqlite+aiosqlite:///./insights_agent.db"
# SESSION_DATABASE_URL not set - uses DATABASE_URL
```

---

## Database Security Architecture

For production deployments, we recommend separating the databases:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     Marketplace Database (Shared)                            │
│                                                                              │
│  ┌────────────────────┐  ┌────────────────────┐  ┌────────────────────┐    │
│  │ marketplace_       │  │ marketplace_       │  │ dcr_clients        │    │
│  │ accounts           │  │ entitlements       │  │                    │    │
│  │ - id               │  │ - id (order_id)    │  │ - client_id        │    │
│  │ - state            │  │ - account_id       │  │ - client_secret    │    │
│  │ - provider_id      │  │ - state            │  │ - order_id         │    │
│  └────────────────────┘  └────────────────────┘  └────────────────────┘    │
│                                                                              │
│  Access: Marketplace Handler (read/write), Agent (read-only for validation) │
└─────────────────────────────────────────────────────────────────────────────┘
                              │
                              │ Order validation (read-only)
                              ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                     Session Database (Per-Agent or Shared)                   │
│                                                                              │
│  ┌────────────────────┐  ┌────────────────────┐  ┌────────────────────┐    │
│  │ sessions           │  │ events             │  │ artifacts          │    │
│  │ - session_id       │  │ - event_id         │  │ - artifact_id      │    │
│  │ - user_id          │  │ - session_id       │  │ - session_id       │    │
│  │ - state            │  │ - content          │  │ - content          │    │
│  └────────────────────┘  └────────────────────┘  └────────────────────┘    │
│                                                                              │
│  Access: Agent only (read/write)                                            │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Security Benefits

| Benefit | Description |
|---------|-------------|
| **Isolation** | Compromised agent can't access marketplace credentials or order data |
| **Least Privilege** | Agent only needs read access to validate orders, not write access |
| **Retention** | Different data retention policies (sessions ephemeral, orders permanent) |
| **Scaling** | Session DB scales with agent traffic, marketplace DB scales with orders |
| **Compliance** | Conversation data can be stored in different region/compliance zone |

### Environment Variables

| Variable | Service | Description |
|----------|---------|-------------|
| `DATABASE_URL` | Both | Marketplace database (accounts, orders, DCR clients) |
| `SESSION_DATABASE_URL` | Agent | Session database (ADK sessions, memory). If empty, uses `DATABASE_URL` |

---

## Database Schema

### Tables

```sql
-- Marketplace accounts (from Pub/Sub procurement events)
CREATE TABLE marketplace_accounts (
    id VARCHAR(255) PRIMARY KEY,
    provider_id VARCHAR(255) NOT NULL,
    state VARCHAR(50) NOT NULL DEFAULT 'pending',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'
);

-- Marketplace entitlements/orders (from Pub/Sub procurement events)
CREATE TABLE marketplace_entitlements (
    id VARCHAR(255) PRIMARY KEY,
    account_id VARCHAR(255) NOT NULL REFERENCES marketplace_accounts(id),
    provider_id VARCHAR(255) NOT NULL,
    product_id VARCHAR(255),
    plan VARCHAR(255),
    state VARCHAR(50) NOT NULL DEFAULT 'pending',
    usage_reporting_id VARCHAR(255),
    offer_start_time TIMESTAMP WITH TIME ZONE,
    offer_end_time TIMESTAMP WITH TIME ZONE,
    cancellation_reason TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'
);

-- DCR registered clients (created via real DCR with Keycloak)
CREATE TABLE dcr_clients (
    client_id VARCHAR(255) PRIMARY KEY,
    client_secret_encrypted TEXT NOT NULL,
    registration_access_token_encrypted TEXT,
    order_id VARCHAR(255) NOT NULL UNIQUE,
    account_id VARCHAR(255) NOT NULL,
    redirect_uris TEXT[],
    grant_types TEXT[] DEFAULT ARRAY['authorization_code', 'refresh_token'],
    keycloak_client_uuid VARCHAR(255),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'
);

-- Usage tracking records (for Service Control reporting)
CREATE TABLE usage_records (
    id SERIAL PRIMARY KEY,
    order_id VARCHAR(255) NOT NULL,
    client_id VARCHAR(255),
    input_tokens INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0,
    request_count INTEGER DEFAULT 0,
    period_start TIMESTAMP WITH TIME ZONE NOT NULL,
    period_end TIMESTAMP WITH TIME ZONE NOT NULL,
    reported BOOLEAN DEFAULT FALSE,
    reported_at TIMESTAMP WITH TIME ZONE,
    report_error TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_entitlements_account ON marketplace_entitlements(account_id);
CREATE INDEX idx_entitlements_state ON marketplace_entitlements(state);
CREATE INDEX idx_dcr_clients_order ON dcr_clients(order_id);
CREATE INDEX idx_usage_order_period ON usage_records(order_id, period_start);
CREATE INDEX idx_usage_unreported ON usage_records(reported) WHERE reported = FALSE;
```

---

## Module Structure

```
src/insights_agent/
├── config/
│   └── settings.py                # DCR_ENABLED, DCR_INITIAL_ACCESS_TOKEN,
│                                  # MARKETPLACE_HANDLER_URL
│
├── db/
│   ├── __init__.py                # Export database components
│   ├── base.py                    # SQLAlchemy engine, session, Base
│   ├── models.py                  # ORM models for all tables
│   └── migrations/                # Alembic migrations (future)
│
├── dcr/
│   ├── __init__.py
│   ├── models.py                  # Pydantic models
│   ├── google_jwt.py              # Google JWT validation
│   ├── keycloak_client.py         # Keycloak DCR API client
│   ├── repository.py              # PostgreSQL DCR client repository
│   ├── service.py                 # DCR business logic
│   └── router.py                  # DCR endpoints (used by handler)
│
├── marketplace/
│   ├── __init__.py
│   ├── models.py                  # Pydantic models
│   ├── repository.py              # PostgreSQL repositories
│   ├── service.py                 # Procurement API integration
│   ├── router.py                  # Marketplace endpoints (used by handler)
│   └── pubsub.py                  # Pub/Sub event handling
│
├── api/                           # AGENT SERVICE (port 8000)
│   ├── app.py                     # FastAPI app factory
│   └── a2a/
│       ├── router.py              # A2A JSON-RPC endpoints
│       └── agent_card.py          # AgentCard with DCR extension pointing
│                                  # to marketplace handler
│
└── ...
```

### Service Entry Points

| Service | Entry Point | Port | Container |
|---------|-------------|------|-----------|
| Marketplace Handler | `python -m insights_agent.marketplace` | 8001 | `marketplace-handler` |
| Insights Agent | `python -m insights_agent` | 8000 | `insights-agent` |

---

## Keycloak DCR Integration

### Red Hat SSO DCR Endpoint

Red Hat SSO (Keycloak) provides DCR at:
```
POST /realms/{realm}/clients-registrations/openid-connect
```

### Initial Access Token

An **Initial Access Token (IAT)** is required to create clients via DCR:
1. Keycloak Admin creates an IAT in the realm settings
2. IAT has limited uses (configurable)
3. Stored in `DCR_INITIAL_ACCESS_TOKEN` environment variable

### DCR Request/Response

**Request** (to Keycloak):
```json
{
  "client_name": "gemini-order-12345",
  "redirect_uris": ["https://example.com/callback"],
  "grant_types": ["authorization_code", "refresh_token"],
  "token_endpoint_auth_method": "client_secret_basic"
}
```

**Response** (from Keycloak):
```json
{
  "client_id": "generated-uuid",
  "client_secret": "generated-secret",
  "client_name": "gemini-order-12345",
  "redirect_uris": ["https://example.com/callback"],
  "registration_access_token": "token-for-updates",
  "registration_client_uri": "https://sso.../clients/uuid"
}
```

### Mapping to Google DCR Response

The Keycloak response is stored and mapped to Google's expected format:
```json
{
  "client_id": "generated-uuid",
  "client_secret": "generated-secret",
  "client_secret_expires_at": 0
}
```

---

## Security Considerations

1. **Secret Encryption**: Client secrets stored in PostgreSQL are encrypted with Fernet
2. **Initial Access Token**: Stored as a secret, not in code
3. **Registration Access Tokens**: Encrypted and stored for future client management
4. **No Secrets in Logs**: All sensitive values redacted in logging

---

## Fallback Mode (DCR Disabled)

When `DCR_ENABLED=false`:

1. DCR endpoints (`/dcr`, `/oauth/register`) return an error or the static client
2. Authentication uses `RED_HAT_SSO_CLIENT_ID` and `RED_HAT_SSO_CLIENT_SECRET`
3. No Keycloak DCR calls are made
4. Suitable for development or when using a pre-registered OAuth client

---

## Two Flows: Procurement vs Registration

The Marketplace Handler handles **two distinct flows** through the same `/dcr` endpoint:

### Flow 1: Procurement (Async, Pub/Sub)

**Triggered by**: Customer purchasing from Google Cloud Marketplace

```
┌─────────────┐     ┌──────────────┐     ┌──────────────┐     ┌─────────────────┐
│  Customer   │────▶│  Marketplace │────▶│   Pub/Sub    │────▶│    Handler      │
│  Purchases  │     │  (Purchase)  │     │   (Push)     │     │    /dcr         │
└─────────────┘     └──────────────┘     └──────────────┘     └────────┬────────┘
                                                                       │
                                                                       ▼
                                                              ┌─────────────────┐
                                                              │ Procurement API │
                                                              │ (Approve)       │
                                                              └────────┬────────┘
                                                                       │
                                                                       ▼
                                                              ┌─────────────────┐
                                                              │   PostgreSQL    │
                                                              │ (Store Account/ │
                                                              │  Entitlement)   │
                                                              └─────────────────┘
```

**Request format** (Pub/Sub wrapper):
```json
{
  "message": {
    "data": "base64-encoded-event",
    "messageId": "123456",
    "publishTime": "2024-01-15T12:00:00Z"
  },
  "subscription": "projects/my-project/subscriptions/marketplace-events"
}
```

**Event types handled**:
- `ACCOUNT_CREATION_REQUESTED` - New customer account
- `ACCOUNT_ACTIVE` - Account approved
- `ENTITLEMENT_CREATION_REQUESTED` - New order
- `ENTITLEMENT_ACTIVE` - Order activated
- `ENTITLEMENT_CANCELLED` - Order cancelled

### Flow 2: Registration (Sync, DCR)

**Triggered by**: Admin configuring agent in Gemini Enterprise

```
┌─────────────┐     ┌──────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   Admin     │────▶│    Gemini    │────▶│    Handler      │────▶│  Red Hat SSO    │
│  Configures │     │  Enterprise  │     │    /dcr         │     │  (Create OAuth  │
│   Agent     │     │  (DCR Call)  │     │                 │     │   Client)       │
└─────────────┘     └──────────────┘     └────────┬────────┘     └────────┬────────┘
                                                  │                       │
                                                  ▼                       │
                                         ┌─────────────────┐              │
                                         │   PostgreSQL    │◀─────────────┘
                                         │ (Verify Order,  │ (Store Client)
                                         │  Store Client)  │
                                         └─────────────────┘
```

**Request format** (DCR):
```json
{
  "software_statement": "eyJhbGciOiJSUzI1NiIs...",
  "redirect_uris": ["https://example.com/callback"]
}
```

**Software statement JWT claims** (signed by Google):
```json
{
  "iss": "https://accounts.google.com",
  "sub": "https://accounts.google.com",
  "order_id": "order-12345",
  "redirect_uris": ["https://example.com/callback"]
}
```

### Hybrid Endpoint Logic

The `/dcr` endpoint routes requests based on content:

```python
@router.post("/dcr")
async def hybrid_dcr_handler(request: Request):
    body = await request.json()

    if "software_statement" in body:
        # DCR path - create OAuth client
        return await _handle_dcr_request(body)
    elif "message" in body:
        # Pub/Sub path - process procurement event
        return await _handle_pubsub_event(body)
    else:
        raise HTTPException(400, "Invalid request format")
```

---

## Deployment

See [deploy/cloudrun/README.md](../deploy/cloudrun/README.md) for deployment instructions.

Deploy both services:
```bash
./deploy/cloudrun/deploy.sh --service all --allow-unauthenticated
```

Deploy only handler:
```bash
./deploy/cloudrun/deploy.sh --service handler --allow-unauthenticated
```

---

## Implementation Checklist

- [x] Add DCR configuration to settings.py
- [x] Create database module (db/base.py, db/models.py)
- [x] Create KeycloakDCRClient (dcr/keycloak_client.py)
- [x] Create DCRClientRepository (dcr/repository.py)
- [x] Update DCRService for real DCR with fallback
- [x] Update marketplace repositories for PostgreSQL
- [x] Update app.py lifespan for database initialization
- [x] Update tests
- [x] Update deployment configuration
- [x] Create separate marketplace-handler service
- [x] Update agent_card.py to point DCR to handler
- [x] Update deployment scripts for two services
