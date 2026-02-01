# Architecture

This document describes the architecture of the Red Hat Insights Agent.

## Overview

The Insights Agent is an A2A-ready (Agent-to-Agent) service that provides AI-powered access to Red Hat Insights. It is built using Google's Agent Development Kit (ADK) and integrates with Red Hat's MCP (Model Context Protocol) server for Insights data access.

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              Client Applications                             │
│                    (Web Apps, CLI Tools, Other Agents)                       │
└─────────────────────────────────────────────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                            Load Balancer / Ingress                           │
│                         (Cloud Run / Kubernetes)                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           Insights Agent Service                             │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │                           FastAPI Application                           ││
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌───────────────┐  ││
│  │  │   A2A API   │  │  OAuth API  │  │   DCR API   │  │  Health/Ready │  ││
│  │  │     /       │  │  /oauth/*   │  │  /register  │  │  /health      │  ││
│  │  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └───────────────┘  ││
│  │         │                │                │                             ││
│  │         ▼                ▼                ▼                             ││
│  │  ┌─────────────────────────────────────────────────────────────────┐   ││
│  │  │                     Authentication Layer                        │   ││
│  │  │              (JWT Validation, JWKS Cache)                       │   ││
│  │  └─────────────────────────────────────────────────────────────────┘   ││
│  │                              │                                          ││
│  │                              ▼                                          ││
│  │  ┌─────────────────────────────────────────────────────────────────┐   ││
│  │  │                        Agent Core                                │   ││
│  │  │                  (Google ADK + Gemini)                          │   ││
│  │  └─────────────────────────────────────────────────────────────────┘   ││
│  │                              │                                          ││
│  │                              ▼                                          ││
│  │  ┌─────────────────────────────────────────────────────────────────┐   ││
│  │  │                      MCP Integration                             │   ││
│  │  │              (Red Hat Insights MCP Client)                       │   ││
│  │  └─────────────────────────────────────────────────────────────────┘   ││
│  └─────────────────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────────────────┘
         │                    │                    │
         ▼                    ▼                    ▼
┌─────────────┐      ┌─────────────┐      ┌─────────────┐
│   Gemini    │      │  Red Hat    │      │  PostgreSQL │
│     API     │      │  Insights   │      │  Database   │
│  (Vertex)   │      │  MCP Server │      │  (optional) │
└─────────────┘      └─────────────┘      └─────────────┘
                            │
                            ▼
                     ┌─────────────┐
                     │  Red Hat    │
                     │  Insights   │
                     │    APIs     │
                     └─────────────┘
```

## Components

### FastAPI Application

The main web application built with FastAPI, providing:

- **A2A Endpoints**: Agent-to-Agent protocol implementation
- **OAuth Endpoints**: Authorization Code flow with Red Hat SSO
- **DCR Endpoint**: Dynamic Client Registration for marketplace clients
- **Health Endpoints**: Kubernetes-compatible health and readiness checks

### Authentication Layer

Handles all authentication and authorization:

- **JWT Validation**: Validates tokens from Red Hat SSO
- **JWKS Cache**: Caches public keys with automatic refresh
- **Scope Checking**: Validates required scopes for protected endpoints

### Agent Core

The AI agent built with Google ADK:

- **Gemini Model**: Uses Gemini 2.5 Flash for natural language understanding
- **Tool Orchestration**: Manages tool calls to MCP server
- **Session Management**: Maintains conversation context

### MCP Integration

Connects to Red Hat Insights via MCP:

- **Tool Discovery**: Discovers available Insights tools
- **Tool Execution**: Executes tools and returns results
- **Authentication**: Handles service account authentication

## Data Flow

### User Query Flow

```
1. User sends query to / endpoint (A2A JSON-RPC)
2. JWT token validated against Red Hat SSO
3. Query passed to Agent Core
4. Agent processes query with Gemini
5. Agent calls MCP tools as needed
6. MCP tools query Red Hat Insights APIs
7. Results aggregated and returned to user
```

### OAuth Flow

```
1. Client redirected to /oauth/authorize
2. User redirected to Red Hat SSO
3. User authenticates and consents
4. SSO redirects to /oauth/callback with code
5. Agent exchanges code for tokens
6. Tokens returned to client
```

### DCR Flow

```
1. Marketplace client calls /oauth/register
2. Agent validates request signature
3. Client credentials created in database
4. Credentials returned to client
5. Client uses credentials for token requests
```

## Module Structure

```
src/insights_agent/
├── api/                    # API layer
│   ├── app.py             # FastAPI application factory
│   ├── a2a.py             # A2A protocol endpoints
│   └── models.py          # API request/response models
├── auth/                   # Authentication
│   ├── jwt.py             # JWT validation and JWKS
│   ├── oauth.py           # OAuth client
│   ├── router.py          # OAuth endpoints
│   ├── dependencies.py    # FastAPI dependencies
│   └── models.py          # Auth data models
├── config/                 # Configuration
│   └── settings.py        # Pydantic settings
├── core/                   # Agent core
│   └── agent.py           # ADK agent definition
├── db/                     # Database
│   └── models.py          # SQLAlchemy models
├── metering/              # Usage tracking
│   └── tracker.py         # Usage metering
└── tools/                 # MCP integration
    ├── mcp_config.py      # MCP server configuration
    └── skills.py          # Agent skills definition
```

## External Dependencies

| Service | Purpose | Required |
|---------|---------|----------|
| Google Gemini | AI model for agent | Yes |
| Red Hat SSO | User authentication | Yes |
| Red Hat Insights MCP | Data access | Yes |
| PostgreSQL | Data persistence | Optional |
| Google Cloud Service Control | Usage reporting | Production |

## Scaling Considerations

### Horizontal Scaling

- Agent is stateless and can scale horizontally
- Session state stored in database (optional)
- Rate limits enforced in-memory (per instance)

### Resource Requirements

| Deployment | CPU | Memory | Notes |
|------------|-----|--------|-------|
| Development | 1 | 512Mi | Minimal for testing |
| Production | 2 | 2Gi | Recommended baseline |
| High Load | 4 | 4Gi | For high concurrency |

### Connection Pooling

- Database connections pooled via SQLAlchemy
- HTTP connections to external services pooled via httpx

## Security

### Authentication

- All A2A endpoints require valid JWT
- Tokens validated against Red Hat SSO JWKS
- Token claims verified (issuer, audience, expiration)

### Authorization

- Scope-based access control
- Client ID extracted for usage tracking
- Organization ID used for multi-tenancy

### Secrets Management

- Secrets stored in environment variables
- Production uses Google Secret Manager
- No secrets in code or configuration files

### Network Security

- HTTPS enforced in production
- CORS configured for allowed origins
- Rate limiting prevents abuse
