# Authentication

This document describes the authentication mechanisms used by the Insights Agent.

## Overview

The Insights Agent uses OAuth 2.0 with Red Hat SSO (sso.redhat.com) as the identity provider. This enables secure authentication for Red Hat customers accessing the agent.

## OAuth 2.0 Authorization Code Flow

The agent implements the standard OAuth 2.0 Authorization Code Grant flow:

```
┌──────────┐                                    ┌──────────────┐
│  Client  │                                    │ Insights     │
│  App     │                                    │ Agent        │
└────┬─────┘                                    └──────┬───────┘
     │                                                 │
     │  1. GET /oauth/authorize                        │
     │  ─────────────────────────────────────────────► │
     │                                                 │
     │  2. Redirect to Red Hat SSO                     │
     │  ◄───────────────────────────────────────────── │
     │                                                 │
     │         ┌─────────────────┐                     │
     │         │   Red Hat SSO   │                     │
     │         └────────┬────────┘                     │
     │                  │                              │
     │  3. Login page   │                              │
     │  ◄───────────────┤                              │
     │                  │                              │
     │  4. User logs in │                              │
     │  ────────────────►                              │
     │                  │                              │
     │  5. Redirect with authorization code            │
     │  ◄───────────────┤                              │
     │                  │                              │
     │  6. GET /oauth/callback?code=...                │
     │  ─────────────────────────────────────────────► │
     │                                                 │
     │                                    7. Exchange  │
     │                                       code for  │
     │                                       tokens    │
     │                                                 │
     │  8. Return tokens                               │
     │  ◄───────────────────────────────────────────── │
     │                                                 │
```

## Endpoints

### GET /oauth/authorize

Initiates the OAuth flow by redirecting to Red Hat SSO.

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `response_type` | string | No | Must be "code" (default) |
| `client_id` | string | No | Client ID (uses configured default) |
| `redirect_uri` | string | No | Redirect URI after auth |
| `scope` | string | No | OAuth scopes (default: "openid profile email") |
| `state` | string | No | CSRF protection state |

**Example:**

```bash
curl -L "http://localhost:8000/oauth/authorize?state=random123"
```

### GET /oauth/callback

Handles the callback from Red Hat SSO after user authentication.

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `code` | string | Yes | Authorization code from SSO |
| `state` | string | Yes | State parameter for CSRF validation |

**Response:**

```json
{
  "access_token": "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "Bearer",
  "expires_in": 3600,
  "refresh_token": "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...",
  "scope": "openid profile email"
}
```

### POST /oauth/token

Token endpoint for exchanging codes or refreshing tokens.

**Request (Authorization Code):**

```bash
curl -X POST http://localhost:8000/oauth/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=authorization_code" \
  -d "code=AUTHORIZATION_CODE" \
  -d "redirect_uri=http://localhost:8000/oauth/callback"
```

**Request (Refresh Token):**

```bash
curl -X POST http://localhost:8000/oauth/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=refresh_token" \
  -d "refresh_token=REFRESH_TOKEN"
```

**Response:**

```json
{
  "access_token": "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "Bearer",
  "expires_in": 3600,
  "refresh_token": "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

### GET /oauth/userinfo

Returns user information for the authenticated user.

**Request:**

```bash
curl http://localhost:8000/oauth/userinfo \
  -H "Authorization: Bearer ACCESS_TOKEN"
```

**Response:**

```json
{
  "sub": "f:12345678-1234-1234-1234-123456789abc:username",
  "preferred_username": "user@example.com",
  "email": "user@example.com",
  "name": "John Doe",
  "org_id": "12345678"
}
```

## JWT Token Validation

All protected endpoints validate JWT access tokens from Red Hat SSO.

### Validation Process

1. **Extract Token**: Token extracted from `Authorization: Bearer <token>` header
2. **Decode Header**: JWT header decoded to get key ID (`kid`)
3. **Fetch JWKS**: Public keys fetched from Red Hat SSO JWKS endpoint
4. **Verify Signature**: Token signature verified using RSA public key
5. **Validate Claims**: Standard claims validated:
   - `iss` (issuer) matches Red Hat SSO
   - `aud` (audience) matches configured client ID
   - `exp` (expiration) is in the future
   - `iat` (issued at) is in the past

### Token Claims

The agent extracts the following claims from validated tokens:

| Claim | Description | Usage |
|-------|-------------|-------|
| `sub` | Subject (user ID) | User identification |
| `azp` | Authorized party | Client ID for usage tracking |
| `preferred_username` | Username | Display name |
| `email` | Email address | User contact |
| `org_id` | Organization ID | Multi-tenancy |
| `scope` | Granted scopes | Authorization |

### JWKS Caching

Public keys are cached to avoid repeated fetches:

- Cache TTL: 1 hour
- Automatic refresh on cache miss
- Force refresh if key not found

## Using Authentication in API Calls

### A2A Endpoints

All A2A endpoints require authentication:

```bash
# Get access token first (via OAuth flow or service account)
ACCESS_TOKEN="your-access-token"

# Call A2A endpoint
curl -X POST http://localhost:8000/a2a \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "method": "message/send",
    "params": {
      "message": {
        "role": "user",
        "parts": [{"type": "text", "text": "List my systems"}]
      }
    },
    "id": "1"
  }'
```

### Protected vs Public Endpoints

| Endpoint | Authentication |
|----------|----------------|
| `GET /health` | Public |
| `GET /ready` | Public |
| `GET /.well-known/agent.json` | Public |
| `GET /oauth/authorize` | Public |
| `GET /oauth/callback` | Public |
| `POST /oauth/token` | Public |
| `GET /oauth/userinfo` | Required |
| `POST /a2a` | Required |
| `POST /a2a/stream` | Required |

## Red Hat SSO Configuration

### Required Settings

```bash
# Red Hat SSO issuer URL
RED_HAT_SSO_ISSUER=https://sso.redhat.com/auth/realms/redhat-external

# OAuth client credentials (register at console.redhat.com)
RED_HAT_SSO_CLIENT_ID=your-client-id
RED_HAT_SSO_CLIENT_SECRET=your-client-secret

# Callback URL (must match registered redirect URI)
RED_HAT_SSO_REDIRECT_URI=http://localhost:8000/oauth/callback

# JWKS endpoint for token validation
RED_HAT_SSO_JWKS_URI=https://sso.redhat.com/auth/realms/redhat-external/protocol/openid-connect/certs
```

### Registering an OAuth Client

1. Go to [console.redhat.com](https://console.redhat.com)
2. Navigate to Settings → Service Accounts
3. Create a new service account
4. Note the client ID and secret
5. Configure redirect URIs

## Development Mode

For local development, JWT validation can be skipped:

```bash
# .env
SKIP_JWT_VALIDATION=true
DEBUG=true
```

**Warning**: Never enable this in production!

When validation is skipped, a default development user is created:

```json
{
  "user_id": "dev-user",
  "client_id": "dev-client",
  "username": "developer",
  "email": "dev@example.com"
}
```

## Local Testing Guide

This section provides step-by-step instructions for testing OAuth authentication locally.

### Prerequisites

Before testing, ensure you have:

1. The agent installed and configured
2. Red Hat SSO client credentials (or use development mode)
3. Python virtual environment activated

### Option 1: Testing with Development Mode (No Real SSO)

This is the easiest way to test the authentication flow without needing real Red Hat SSO credentials.

1. **Configure development mode** in `.env`:
   ```bash
   # Enable development mode
   SKIP_JWT_VALIDATION=true
   DEBUG=true

   # These can be placeholder values in dev mode
   RED_HAT_SSO_CLIENT_ID=dev-client
   RED_HAT_SSO_CLIENT_SECRET=dev-secret
   RED_HAT_SSO_REDIRECT_URI=http://localhost:8000/oauth/callback
   ```

2. **Start the API server**:
   ```bash
   python -m insights_agent.main
   ```

3. **Test the health endpoint**:
   ```bash
   curl http://localhost:8000/health
   # Expected: {"status": "healthy"}
   ```

4. **Test userinfo with any token** (dev mode accepts any token):
   ```bash
   curl http://localhost:8000/oauth/userinfo \
     -H "Authorization: Bearer any-token-works-in-dev-mode"
   ```

   Expected response:
   ```json
   {
     "sub": "dev-user",
     "preferred_username": "developer",
     "email": "dev@example.com",
     "client_id": "dev-client"
   }
   ```

5. **Test A2A endpoint with authentication**:
   ```bash
   curl -X POST http://localhost:8000/a2a \
     -H "Authorization: Bearer dev-token" \
     -H "Content-Type: application/json" \
     -d '{
       "jsonrpc": "2.0",
       "method": "message/send",
       "params": {
         "message": {
           "role": "user",
           "parts": [{"type": "text", "text": "Hello"}]
         }
       },
       "id": "1"
     }'
   ```

### Option 2: Testing with Real Red Hat SSO

For integration testing with real Red Hat SSO authentication:

1. **Configure real SSO credentials** in `.env`:
   ```bash
   # Disable development mode
   SKIP_JWT_VALIDATION=false
   DEBUG=false

   # Real Red Hat SSO configuration
   RED_HAT_SSO_ISSUER=https://sso.redhat.com/auth/realms/redhat-external
   RED_HAT_SSO_CLIENT_ID=your-registered-client-id
   RED_HAT_SSO_CLIENT_SECRET=your-client-secret
   RED_HAT_SSO_REDIRECT_URI=http://localhost:8000/oauth/callback
   RED_HAT_SSO_JWKS_URI=https://sso.redhat.com/auth/realms/redhat-external/protocol/openid-connect/certs
   ```

2. **Start the API server**:
   ```bash
   python -m insights_agent.main
   ```

3. **Initiate the OAuth flow** - Open in browser:
   ```
   http://localhost:8000/oauth/authorize
   ```

   This will redirect you to Red Hat SSO login page.

4. **Complete login** at Red Hat SSO:
   - Enter your Red Hat credentials
   - Authorize the application if prompted

5. **Handle the callback**:
   - After successful login, you'll be redirected to `/oauth/callback`
   - The response will contain your access token and refresh token
   - Save the access token for subsequent requests

6. **Test authenticated endpoints**:
   ```bash
   # Replace with your actual access token
   ACCESS_TOKEN="eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9..."

   # Test userinfo
   curl http://localhost:8000/oauth/userinfo \
     -H "Authorization: Bearer $ACCESS_TOKEN"

   # Test A2A endpoint
   curl -X POST http://localhost:8000/a2a \
     -H "Authorization: Bearer $ACCESS_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{
       "jsonrpc": "2.0",
       "method": "message/send",
       "params": {
         "message": {
           "role": "user",
           "parts": [{"type": "text", "text": "List my systems"}]
         }
       },
       "id": "1"
     }'
   ```

### Option 3: Browser-Based Testing

For a more interactive testing experience:

1. **Start the server** with debug mode for detailed logging:
   ```bash
   DEBUG=true python -m insights_agent.main
   ```

2. **Open browser developer tools** (F12) to monitor network requests

3. **Navigate to the authorize endpoint**:
   ```
   http://localhost:8000/oauth/authorize?state=test123
   ```

4. **Follow the OAuth flow**:
   - You'll be redirected to Red Hat SSO
   - Login with your credentials
   - Observe the redirect back to your callback URL
   - Check the network tab for the token response

5. **Use browser console to make authenticated requests**:
   ```javascript
   // After getting your token from the callback
   const token = "your-access-token";

   fetch("http://localhost:8000/oauth/userinfo", {
     headers: { "Authorization": `Bearer ${token}` }
   })
   .then(r => r.json())
   .then(console.log);
   ```

### Testing Token Refresh

To test the token refresh flow:

1. **Get initial tokens** via the authorization flow (see above)

2. **Use the refresh token** to get new tokens:
   ```bash
   curl -X POST http://localhost:8000/oauth/token \
     -H "Content-Type: application/x-www-form-urlencoded" \
     -d "grant_type=refresh_token" \
     -d "refresh_token=YOUR_REFRESH_TOKEN"
   ```

3. **Verify the new access token works**:
   ```bash
   curl http://localhost:8000/oauth/userinfo \
     -H "Authorization: Bearer NEW_ACCESS_TOKEN"
   ```

### Testing Error Scenarios

Test how the system handles authentication errors:

1. **Missing Authorization header**:
   ```bash
   curl http://localhost:8000/oauth/userinfo
   # Expected: 401 Unauthorized
   ```

2. **Invalid token**:
   ```bash
   curl http://localhost:8000/oauth/userinfo \
     -H "Authorization: Bearer invalid-token"
   # Expected: 401 Unauthorized (in production mode)
   ```

3. **Expired token** (use a known expired token):
   ```bash
   curl http://localhost:8000/oauth/userinfo \
     -H "Authorization: Bearer EXPIRED_TOKEN"
   # Expected: 401 with "Token has expired" message
   ```

4. **Malformed Authorization header**:
   ```bash
   curl http://localhost:8000/oauth/userinfo \
     -H "Authorization: InvalidFormat token123"
   # Expected: 401 Unauthorized
   ```

### Troubleshooting

#### "Invalid redirect URI" error

Ensure `RED_HAT_SSO_REDIRECT_URI` in your `.env` matches exactly what's registered in Red Hat SSO:
- Check for trailing slashes
- Verify http vs https
- Confirm the port number

#### "Token validation failed" error

1. Check that `RED_HAT_SSO_JWKS_URI` is correct
2. Verify network connectivity to sso.redhat.com
3. Ensure the token hasn't expired
4. Check that the audience claim matches your client ID

#### "CORS errors" in browser

If testing from a browser on a different origin, you may need to configure CORS. The agent should handle this, but verify your browser isn't blocking requests.

#### Server not starting

Check the logs for configuration errors:
```bash
# Run with debug logging
LOG_LEVEL=DEBUG python -m insights_agent.main
```

### Automated Testing

The project includes unit tests for authentication:

```bash
# Run all auth tests
pytest tests/test_auth.py -v

# Run specific test
pytest tests/test_auth.py::TestJWTValidator -v

# Run with coverage
pytest tests/test_auth.py --cov=insights_agent.auth
```

## Error Handling

### Authentication Errors

| HTTP Status | Error | Description |
|-------------|-------|-------------|
| 401 | Missing credentials | No Authorization header |
| 401 | Invalid token | Token signature invalid |
| 401 | Token expired | Token `exp` claim in past |
| 401 | Invalid issuer | Token not from Red Hat SSO |
| 401 | Invalid audience | Token not for this client |
| 403 | Insufficient scope | Missing required scope |

### Error Response Format

```json
{
  "detail": "Token has expired"
}
```

With WWW-Authenticate header:

```
WWW-Authenticate: Bearer
```

## Security Best Practices

1. **Always use HTTPS** in production
2. **Never log tokens** - use token IDs for debugging
3. **Validate all claims** - don't skip validation
4. **Use short token lifetimes** - refresh tokens as needed
5. **Rotate secrets regularly** - update client secrets periodically
6. **Monitor for anomalies** - track failed authentication attempts
