# Troubleshooting Guide

This guide helps diagnose and resolve common issues with the Insights Agent.

## Quick Diagnostics

### Health Check

```bash
# Check if agent is running
curl http://localhost:8000/health

# Expected response
{"status": "healthy", "agent": "insights-agent"}
```

### Readiness Check

```bash
# Check if agent is ready to accept requests
curl http://localhost:8000/ready

# Expected response
{"status": "ready", "agent": "insights-agent"}
```

### View Logs

```bash
# Local development
python -m insights_agent.main 2>&1 | tee agent.log

# Podman
podman logs insights-agent-pod-insights-agent

# Cloud Run
gcloud run logs read insights-agent --region=us-central1
```

## Startup Issues

### Agent Fails to Start

**Symptom**: Agent exits immediately after starting

**Check Configuration**:

```bash
# Validate environment
python -c "from insights_agent.config import get_settings; print(get_settings())"
```

**Common Causes**:

| Error | Cause | Solution |
|-------|-------|----------|
| `ValidationError: google_api_key` | Missing API key | Set `GOOGLE_API_KEY` |
| `ValidationError: lightspeed_client_id` | Missing MCP credentials | Set `LIGHTSPEED_CLIENT_ID` |
| `Connection refused` | Database not running | Start PostgreSQL/Redis |

### Port Already in Use

**Symptom**: `Address already in use`

```bash
# Find process using port 8000
lsof -i :8000

# Kill the process
kill -9 <PID>

# Or use a different port
AGENT_PORT=8001 python -m insights_agent.main
```

### Import Errors

**Symptom**: `ModuleNotFoundError`

```bash
# Ensure virtual environment is activated
source .venv/bin/activate

# Reinstall dependencies
pip install -e ".[dev]"
```

## Authentication Issues

### 401 Unauthorized

**Symptom**: All authenticated requests return 401

**Check Token**:

```bash
# Decode JWT (without verification)
echo $TOKEN | cut -d. -f2 | base64 -d 2>/dev/null | jq .
```

**Common Causes**:

| Issue | Cause | Solution |
|-------|-------|----------|
| Token expired | `exp` in past | Get new token via OAuth |
| Wrong audience | Token for different client | Use correct client_id |
| Wrong issuer | Token from different IdP | Use Red Hat SSO |
| Invalid signature | Key rotation | Clear JWKS cache |

**Force JWKS Refresh**:

```bash
# Restart the agent to clear JWKS cache
# Or wait for cache TTL (1 hour)
```

### 403 Forbidden

**Symptom**: Authenticated but access denied

**Check Scopes**:

```bash
# Decode token and check scope claim
echo $TOKEN | cut -d. -f2 | base64 -d | jq .scope
```

**Required Scopes**: `openid profile email`

### OAuth Callback Errors

**Symptom**: Callback fails with error

| Error | Cause | Solution |
|-------|-------|----------|
| `invalid_grant` | Code expired or reused | Restart OAuth flow |
| `redirect_uri_mismatch` | URI doesn't match registered | Update redirect URI |
| `invalid_client` | Wrong client credentials | Check client_id/secret |

### JWKS Fetch Failures

**Symptom**: `Failed to fetch JWKS`

```bash
# Test JWKS endpoint
curl https://sso.redhat.com/auth/realms/redhat-external/protocol/openid-connect/certs
```

**Causes**:
- Network connectivity issues
- Firewall blocking outbound HTTPS
- SSO service unavailable

## Agent/AI Issues

### No Response from Agent

**Symptom**: Agent returns empty response

**Check Gemini Connection**:

```bash
# Test Gemini API directly
curl -X POST "https://generativelanguage.googleapis.com/v1/models/gemini-2.5-flash:generateContent?key=$GOOGLE_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"contents":[{"parts":[{"text":"Hello"}]}]}'
```

**Common Causes**:

| Issue | Cause | Solution |
|-------|-------|----------|
| API quota exceeded | Too many requests | Wait or increase quota |
| Invalid API key | Key revoked/invalid | Generate new key |
| Model not available | Region restriction | Use supported region |

### Slow Responses

**Symptom**: Requests take > 30 seconds

**Causes**:
- Cold start (first request after idle)
- Complex queries requiring multiple tool calls
- MCP server latency

**Solutions**:
- Set `min-instances=1` in Cloud Run
- Enable CPU boost for startup
- Add request timeouts

### Tool Execution Failures

**Symptom**: `Tool execution failed`

**Check MCP Connection**:

```bash
# Test MCP server (if using HTTP transport)
curl http://localhost:8080/health

# Check MCP credentials
echo $LIGHTSPEED_CLIENT_ID
```

**Common Causes**:

| Issue | Cause | Solution |
|-------|-------|----------|
| `Authentication failed` | Invalid credentials | Check LIGHTSPEED_* vars |
| `Connection refused` | MCP server not running | Start MCP server |
| `Timeout` | Network/server issues | Increase timeout |

## Database Issues

### Connection Failures

**Symptom**: `Connection refused` or timeout

**PostgreSQL**:

```bash
# Check PostgreSQL is running
pg_isready -h localhost -p 5432

# Test connection
psql postgresql://insights:insights@localhost:5432/insights_agent
```

**SQLite**:

```bash
# Check database file permissions
ls -la insights_agent.db

# Test with sqlite3
sqlite3 insights_agent.db ".tables"
```

### Migration Errors

**Symptom**: `Table does not exist`

```bash
# Run migrations
alembic upgrade head

# Check current revision
alembic current
```

## Redis Issues

### Connection Failures

**Symptom**: Rate limiting not working

```bash
# Check Redis is running
redis-cli ping

# Test connection
redis-cli -h localhost -p 6379 ping
```

### Rate Limit Not Enforced

**Check Redis Keys**:

```bash
redis-cli keys "rate:*"
redis-cli get "rate:client_id:minute"
```

## Container/Pod Issues

### Pod Won't Start

**Symptom**: Containers crash or restart

```bash
# Check pod status
podman pod ps

# Check container logs
podman logs insights-agent-pod-insights-agent

# Describe pod
podman pod inspect insights-agent-pod
```

### Image Pull Failures

**Symptom**: `Image not found`

```bash
# Login to registry
podman login registry.access.redhat.com

# Pull image manually
podman pull registry.access.redhat.com/ubi9/python-311:latest
```

### Volume Mount Issues

**Symptom**: Config not found

```bash
# Check config directory exists
ls -la ./config/

# Check volume mounts
podman inspect insights-agent-pod-insights-agent | jq '.[].Mounts'
```

## Cloud Run Issues

### Deployment Failures

**Symptom**: Deploy command fails

```bash
# Check Cloud Build logs
gcloud builds list --limit=5

# Get build details
gcloud builds describe BUILD_ID
```

### Service Not Accessible

**Symptom**: 503 Service Unavailable

```bash
# Check service status
gcloud run services describe insights-agent --region=us-central1

# Check revision status
gcloud run revisions list --service=insights-agent --region=us-central1
```

### Cold Start Timeouts

**Symptom**: First request times out

**Solutions**:
1. Set minimum instances:
   ```bash
   gcloud run services update insights-agent --min-instances=1
   ```

2. Enable CPU boost:
   ```bash
   gcloud run services update insights-agent \
     --cpu-boost
   ```

## Performance Issues

### High Latency

**Diagnose**:

```bash
# Time a request
time curl http://localhost:8000/health

# Profile with detailed timing
curl -w "@curl-format.txt" -o /dev/null -s http://localhost:8000/a2a
```

**curl-format.txt**:
```
     time_namelookup:  %{time_namelookup}s\n
        time_connect:  %{time_connect}s\n
     time_appconnect:  %{time_appconnect}s\n
    time_pretransfer:  %{time_pretransfer}s\n
       time_redirect:  %{time_redirect}s\n
  time_starttransfer:  %{time_starttransfer}s\n
          time_total:  %{time_total}s\n
```

### Memory Issues

**Symptom**: OOM kills

```bash
# Monitor memory usage
podman stats insights-agent-pod-insights-agent

# Increase memory limit
# Edit insights-agent-pod.yaml or Cloud Run config
```

## Logging and Debugging

### Enable Debug Logging

```bash
# Set environment variable
LOG_LEVEL=DEBUG python -m insights_agent.main
```

### Enable Debug Mode

```bash
# Enables /docs endpoint
DEBUG=true python -m insights_agent.main

# Access Swagger UI
open http://localhost:8000/docs
```

### Common Log Messages

| Message | Meaning | Action |
|---------|---------|--------|
| `JWT validation failed` | Invalid token | Check token |
| `JWKS fetch failed` | Can't get keys | Check network |
| `Tool execution failed` | MCP error | Check MCP server |
| `Rate limit exceeded` | Too many requests | Wait or upgrade |
| `Database connection failed` | DB unreachable | Check database |

## Getting Help

### Collect Diagnostic Information

Before reporting an issue, collect:

1. **Logs**:
   ```bash
   LOG_LEVEL=DEBUG python -m insights_agent.main 2>&1 | tee debug.log
   ```

2. **Configuration** (redact secrets):
   ```bash
   env | grep -E '^(AGENT|GOOGLE|RED_HAT|MCP|LOG)' | sed 's/=.*/=REDACTED/'
   ```

3. **Version Info**:
   ```bash
   python --version
   pip show insights-agent
   ```

4. **Request/Response** (redact tokens):
   ```bash
   curl -v http://localhost:8000/health 2>&1
   ```

### Report Issues

File issues at: https://github.com/your-org/insights-agent/issues

Include:
- Description of the problem
- Steps to reproduce
- Expected vs actual behavior
- Diagnostic information collected above
