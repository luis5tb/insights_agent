# Architecture

This document describes the architecture of the Red Hat Insights Agent.

## Overview

The Red Hat Insights Agent is an A2A-ready (Agent-to-Agent) service that provides AI-powered access to Red Hat Insights. It is built using Google's Agent Development Kit (ADK) and integrates with Red Hat's MCP (Model Context Protocol) server for Insights data access.

The system consists of **two separate services**:

1. **Marketplace Handler** - Always running service that handles provisioning and client registration
2. **Insights Agent** - The AI agent that handles user interactions (deployed after provisioning)

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              Google Cloud Marketplace                             │
│                    (Gemini Enterprise / Procurement Events)                       │
└─────────────────────────────────────────────────────────────────────────────────┘
         │                                                    │
         │ Pub/Sub Events                                     │ DCR Request
         │ (Account/Entitlement)                              │ (software_statement)
         ▼                                                    ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                          Marketplace Handler Service                              │
│                         (Cloud Run - Always Running)                              │
│  ┌───────────────────────────────────────────────────────────────────────────┐  │
│  │                           FastAPI Application                              │  │
│  │  ┌──────────────────────────────────────────────────────────────────────┐ │  │
│  │  │                    Hybrid /dcr Endpoint                               │ │  │
│  │  │  - Pub/Sub Events → Approve accounts/entitlements                    │ │  │
│  │  │  - DCR Requests → Create OAuth clients via Keycloak                  │ │  │
│  │  └──────────────────────────────────────────────────────────────────────┘ │  │
│  └───────────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────────┘
         │                                                    │
         │ Store                                              │ Create Client
         ▼                                                    ▼
┌─────────────────┐                                  ┌─────────────────────────┐
│   PostgreSQL    │                                  │    Red Hat SSO          │
│   Database      │◀────────────────────────────────▶│    (Keycloak)           │
│  - Accounts     │                                  │  - DCR Endpoint         │
│  - Entitlements │                                  │  - OIDC/OAuth           │
│  - DCR Clients  │                                  └─────────────────────────┘
└─────────────────┘
         ▲
         │ Read/Write
         ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                            Insights Agent Service                                 │
│                  (Cloud Run - Deployed After Provisioning)                        │
│  ┌───────────────────────────────────────────────────────────────────────────┐  │
│  │                           FastAPI Application                              │  │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────────┐   │  │
│  │  │   A2A API   │  │  OAuth API  │  │ Agent Card  │  │  Health/Ready   │   │  │
│  │  │     /       │  │  /oauth/*   │  │ /.well-     │  │  /health        │   │  │
│  │  │  (JSON-RPC) │  │  (callback) │  │  known/     │  │  /ready         │   │  │
│  │  └──────┬──────┘  └──────┬──────┘  │  agent.json │  └─────────────────┘   │  │
│  │         │                │         └─────────────┘                        │  │
│  │         ▼                ▼                                                │  │
│  │  ┌─────────────────────────────────────────────────────────────────┐     │  │
│  │  │                     Authentication Layer                         │     │  │
│  │  │              (JWT Validation via Red Hat SSO)                   │     │  │
│  │  └─────────────────────────────────────────────────────────────────┘     │  │
│  │                              │                                            │  │
│  │                              ▼                                            │  │
│  │  ┌─────────────────────────────────────────────────────────────────┐     │  │
│  │  │                        Agent Core                                │     │  │
│  │  │                  (Google ADK + Gemini)                          │     │  │
│  │  └─────────────────────────────────────────────────────────────────┘     │  │
│  │                              │                                            │  │
│  │                              ▼                                            │  │
│  │  ┌─────────────────────────────────────────────────────────────────┐     │  │
│  │  │                      MCP Sidecar                                  │     │  │
│  │  │              (Red Hat Insights MCP Server)                       │     │  │
│  │  └─────────────────────────────────────────────────────────────────┘     │  │
│  └───────────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────────┘
         │                    │
         ▼                    ▼
┌─────────────┐      ┌─────────────────────────┐
│   Gemini    │      │  Red Hat Insights APIs   │
│     API     │      │  (via MCP Server)        │
│  (Vertex)   │      │  - Advisor               │
└─────────────┘      │  - Vulnerability         │
                     │  - Patch                 │
                     │  - Content               │
                     └─────────────────────────┘
```

## Two-Service Architecture

### Why Two Services?

The system is split into two services for important operational reasons:

| Service | Purpose | Lifecycle |
|---------|---------|-----------|
| **Marketplace Handler** | Handles provisioning and DCR | Always running (minScale=1) |
| **Insights Agent** | AI agent for user queries | Deployed after provisioning |

1. **Marketplace Handler must be always running** to receive Pub/Sub events from Google Cloud Marketplace for account approvals
2. **Agent can be deployed on-demand** after a customer has been provisioned
3. **Separation of concerns**: Provisioning logic is isolated from agent logic
4. **Independent scaling**: Handler scales for provisioning traffic, Agent scales for user traffic

## Components

### Marketplace Handler Service

A separate FastAPI application for provisioning, providing:

- **Hybrid /dcr Endpoint**: Single endpoint handling both:
  - Pub/Sub events (account/entitlement approvals)
  - DCR requests (OAuth client creation)
- **Health Endpoints**: Kubernetes-compatible health checks
- **Database Access**: PostgreSQL for persistent storage

### Insights Agent Service

The main AI agent FastAPI application, providing:

- **A2A Endpoints**: Agent-to-Agent protocol implementation (JSON-RPC)
- **Agent Card**: `/.well-known/agent.json` with capabilities and DCR extension
- **OAuth Endpoints**: Authorization Code callback for user authentication
- **Health Endpoints**: Kubernetes-compatible health and readiness checks

### Authentication Layer

Handles all authentication and authorization:

- **JWT Validation**: Validates tokens from Red Hat SSO
- **JWKS Cache**: Caches public keys with automatic refresh
- **Scope Checking**: Validates required scopes for protected endpoints
- **Bypass for Discovery**: `/.well-known/agent.json` is public per A2A spec

### Agent Core

The AI agent built with Google ADK:

- **Gemini Model**: Uses Gemini 2.5 Flash for natural language understanding
- **Tool Orchestration**: Manages tool calls to MCP server
- **Session Management**: Maintains conversation context

### MCP Sidecar

Runs as a sidecar container connecting to Red Hat Insights:

- **Tool Discovery**: Discovers available Insights tools
- **Tool Execution**: Executes tools and returns results
- **Authentication**: Handles service account authentication to Red Hat APIs

## Data Flow

### Flow 1: Marketplace Procurement (Async)

This flow happens when a customer purchases from Google Cloud Marketplace:

```
1. Customer purchases from Google Cloud Marketplace
2. Marketplace sends Pub/Sub event to Marketplace Handler
3. Handler receives POST /dcr with Pub/Sub message wrapper
4. Handler extracts event type (ACCOUNT_ACTIVE, ENTITLEMENT_ACTIVE, etc.)
5. Handler calls Google Procurement API to approve account/entitlement
6. Handler stores account/entitlement in PostgreSQL
7. Customer is now provisioned for the service
```

```
┌─────────────┐     ┌──────────────┐     ┌─────────────────┐     ┌────────────┐
│  Customer   │────▶│   Marketplace │────▶│    Pub/Sub      │────▶│  Handler   │
│  Purchases  │     │   (Purchase)  │     │  (Event Push)   │     │  /dcr      │
└─────────────┘     └──────────────┘     └─────────────────┘     └─────┬──────┘
                                                                       │
                                         ┌─────────────────┐           │
                                         │   PostgreSQL    │◀──────────┤
                                         │   (Store)       │           │
                                         └─────────────────┘           │
                                                                       ▼
                                         ┌─────────────────────────────────────┐
                                         │   Google Procurement API            │
                                         │   (Approve Account/Entitlement)     │
                                         └─────────────────────────────────────┘
```

### Flow 2: Dynamic Client Registration (Sync)

This flow happens when an admin configures the agent in Gemini Enterprise:

```
1. Admin configures agent in Gemini Enterprise
2. Gemini sends POST /dcr with software_statement JWT
3. Handler validates Google's JWT signature
4. Handler verifies order_id matches a provisioned entitlement
5. Handler calls Red Hat SSO DCR to create OAuth client
6. Handler stores client mapping in PostgreSQL
7. Handler returns client_id, client_secret to Gemini
8. Gemini stores credentials for future OAuth flows
```

```
┌─────────────┐     ┌──────────────┐     ┌─────────────────┐     ┌────────────┐
│   Admin     │────▶│    Gemini    │────▶│   POST /dcr     │────▶│  Handler   │
│  Configures │     │  Enterprise  │     │ software_stmt   │     │  /dcr      │
└─────────────┘     └──────────────┘     └─────────────────┘     └─────┬──────┘
                                                                       │
                           ┌───────────────────────────────────────────┤
                           │                                           │
                           ▼                                           ▼
                    ┌─────────────────┐                    ┌─────────────────┐
                    │   PostgreSQL    │                    │  Red Hat SSO    │
                    │   (Check Order) │                    │  (Create OAuth  │
                    │   (Store Client)│                    │   Client)       │
                    └─────────────────┘                    └─────────────────┘
```

### Flow 3: User Authentication (OAuth)

This flow happens when a user interacts with the agent:

```
1. User/Gemini initiates OAuth flow with client credentials
2. User redirected to Red Hat SSO for authentication
3. User authenticates with Red Hat account
4. SSO redirects to Agent /oauth/callback with code
5. Agent exchanges code for tokens
6. Tokens returned to client for API access
```

### Flow 4: User Query (A2A)

This flow handles actual user interactions with the agent:

```
1. User sends query to / endpoint (A2A JSON-RPC)
2. JWT token validated against Red Hat SSO
3. Query passed to Agent Core
4. Agent processes query with Gemini
5. Agent calls MCP tools as needed
6. MCP sidecar queries Red Hat Insights APIs
7. Results aggregated and returned to user
```

## Module Structure

```
src/insights_agent/
├── api/                        # Agent API layer
│   ├── app.py                 # FastAPI application factory (Agent)
│   ├── a2a/                   # A2A protocol
│   │   ├── router.py          # A2A JSON-RPC endpoints
│   │   └── agent_card.py      # AgentCard builder
│   └── models.py              # API request/response models
├── auth/                       # Authentication (shared)
│   ├── jwt.py                 # JWT validation and JWKS
│   ├── oauth.py               # OAuth client
│   ├── router.py              # OAuth endpoints (callback)
│   ├── dependencies.py        # FastAPI dependencies
│   └── models.py              # Auth data models
├── config/                     # Configuration (shared)
│   └── settings.py            # Pydantic settings
├── core/                       # Agent core
│   └── agent.py               # ADK agent definition
├── db/                         # Database (shared)
│   ├── base.py                # SQLAlchemy engine and Base
│   └── models.py              # ORM models
├── dcr/                        # Dynamic Client Registration
│   ├── google_jwt.py          # Google JWT validation
│   ├── keycloak_client.py     # Keycloak DCR API client
│   ├── models.py              # DCR Pydantic models
│   ├── repository.py          # PostgreSQL repository
│   ├── router.py              # DCR endpoints
│   └── service.py             # DCR business logic
├── marketplace/                # Marketplace integration
│   ├── models.py              # Marketplace Pydantic models
│   ├── pubsub.py              # Pub/Sub event handling
│   ├── repository.py          # PostgreSQL repositories
│   ├── router.py              # Marketplace endpoints
│   └── service.py             # Procurement API integration
│   ├── app.py                 # Handler FastAPI app factory (port 8001)
│   ├── router.py              # Hybrid /dcr endpoint
│   └── __main__.py            # Entry point: python -m insights_agent.marketplace
├── metering/                   # Usage tracking
│   └── tracker.py             # Usage metering
└── tools/                      # MCP integration
    ├── mcp_config.py          # MCP server configuration
    └── skills.py              # Agent skills definition
```

### Container Images

| Image | Service | Port | Purpose |
|-------|---------|------|---------|
| `insights-agent` | Agent | 8000 | A2A protocol, user queries |
| `marketplace-handler` | Handler | 8001 | Pub/Sub events, DCR |
| `insights-mcp` | MCP Sidecar | 8081 | Red Hat Insights tools |

## External Dependencies

| Service | Used By | Purpose | Required |
|---------|---------|---------|----------|
| Google Gemini | Agent | AI model for queries | Yes |
| Red Hat SSO | Both | User authentication, DCR | Yes |
| Red Hat Insights MCP | Agent | Data access | Yes |
| PostgreSQL | Both | Data persistence | Yes (Production) |
| Google Cloud Pub/Sub | Handler | Marketplace events | Production |
| Google Procurement API | Handler | Account/entitlement approval | Production |
| Google Service Control | Agent | Usage reporting | Production |

## Scaling Considerations

### Horizontal Scaling

- Both services are stateless and can scale horizontally
- State stored in PostgreSQL (shared by both services)
- Rate limits enforced in-memory (per instance)

### Service Scaling Requirements

| Service | Min Instances | Max Instances | Notes |
|---------|---------------|---------------|-------|
| Marketplace Handler | 1 | 5 | Always running for Pub/Sub |
| Insights Agent | 0 | 10 | Scale to zero when idle |

### Resource Requirements

| Service | CPU | Memory | Notes |
|---------|-----|--------|-------|
| Marketplace Handler | 1 | 512Mi | Lightweight, event-driven |
| Insights Agent | 2 | 2Gi | AI processing, MCP calls |
| MCP Sidecar | 0.5 | 256Mi | Red Hat Insights queries |

### Connection Pooling

- Database connections pooled via SQLAlchemy
- HTTP connections to external services pooled via httpx
- Both services share the same PostgreSQL database

## Security

### Authentication

- A2A query endpoints require valid JWT from Red Hat SSO
- Tokens validated against Red Hat SSO JWKS
- Token claims verified (issuer, audience, expiration)

### Public Endpoints

Certain endpoints must be publicly accessible per A2A protocol:

| Service | Endpoint | Reason |
|---------|----------|--------|
| Agent | `/.well-known/agent.json` | A2A discovery (no auth per spec) |
| Agent | `/oauth/callback` | OAuth redirect from SSO |
| Handler | `/dcr` | Pub/Sub push and DCR requests |
| Handler | `/health` | Health checks |

Both services are deployed with `--allow-unauthenticated` on Cloud Run.
Authentication is enforced at the **application layer** via OAuth middleware.

### Authorization

- Scope-based access control for authenticated endpoints
- Client ID extracted for usage tracking
- Organization ID used for multi-tenancy
- DCR requests validated via Google JWT signature

### Secrets Management

- Secrets stored in environment variables
- Production uses Google Secret Manager
- No secrets in code or configuration files
- DCR encryption key protects stored client secrets

### Network Security

- HTTPS enforced in production
- CORS configured for allowed origins
- Rate limiting prevents abuse
- Pub/Sub verification via message signature
