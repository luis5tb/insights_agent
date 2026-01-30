# OpenTelemetry Integration

The Insights Agent supports distributed tracing via OpenTelemetry, enabling observability across agent-to-agent interactions and MCP tool calls.

## Overview

When enabled, OpenTelemetry automatically instruments:

- **FastAPI**: Incoming HTTP requests and responses
- **HTTPX**: Outgoing HTTP requests (including MCP calls)
- **A2A SDK**: Agent message processing and task management

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `OTEL_ENABLED` | `false` | Enable OpenTelemetry tracing |
| `OTEL_SERVICE_NAME` | `insights_agent` | Service name for traces |
| `OTEL_EXPORTER_TYPE` | `otlp` | Exporter type (see below) |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `http://localhost:4317` | OTLP gRPC endpoint |
| `OTEL_EXPORTER_OTLP_HTTP_ENDPOINT` | `http://localhost:4318` | OTLP HTTP endpoint |
| `OTEL_TRACES_SAMPLER` | `always_on` | Sampling strategy |
| `OTEL_TRACES_SAMPLER_ARG` | `1.0` | Sampler argument |

### Exporter Types

| Type | Description | Endpoint |
|------|-------------|----------|
| `otlp` | OTLP over gRPC (recommended) | `OTEL_EXPORTER_OTLP_ENDPOINT` |
| `otlp-http` | OTLP over HTTP | `OTEL_EXPORTER_OTLP_HTTP_ENDPOINT` |
| `jaeger` | Jaeger Thrift | Requires `opentelemetry-exporter-jaeger` |
| `zipkin` | Zipkin JSON | Requires `opentelemetry-exporter-zipkin` |
| `console` | Print to stdout | For debugging |

### Sampling Strategies

| Strategy | Description |
|----------|-------------|
| `always_on` | Trace all requests (development) |
| `always_off` | Disable tracing |
| `traceidratio` | Sample X% of requests (use `OTEL_TRACES_SAMPLER_ARG`) |
| `parentbased_always_on` | Trace if parent is traced, otherwise always |
| `parentbased_always_off` | Trace if parent is traced, otherwise never |
| `parentbased_traceidratio` | Trace if parent is traced, otherwise sample |

## Quick Start

### 1. Enable Telemetry

```bash
# In .env
OTEL_ENABLED=true
OTEL_EXPORTER_TYPE=console  # For debugging
```

### 2. Run with Jaeger (Local Development)

Start Jaeger:

```bash
podman run -d --name jaeger \
  -p 4317:4317 \
  -p 4318:4318 \
  -p 16686:16686 \
  jaegertracing/jaeger:latest
```

Configure the agent:

```bash
OTEL_ENABLED=true
OTEL_EXPORTER_TYPE=otlp
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
```

View traces at: http://localhost:16686

### 3. Run with Grafana Tempo (Local Development)

Grafana Tempo is a high-scale distributed tracing backend. Run Tempo with Grafana for visualization:

**Option A: Quick Start with Tempo Standalone**

```bash
# Create Tempo config
cat > tempo-config.yaml << 'EOF'
server:
  http_listen_port: 3200

distributor:
  receivers:
    otlp:
      protocols:
        grpc:
          endpoint: 0.0.0.0:4317
        http:
          endpoint: 0.0.0.0:4318

storage:
  trace:
    backend: local
    local:
      path: /tmp/tempo/blocks
EOF

# Run Tempo
podman run -d --name tempo \
  -p 3200:3200 \
  -p 4317:4317 \
  -p 4318:4318 \
  -v ./tempo-config.yaml:/etc/tempo.yaml \
  grafana/tempo:latest \
  -config.file=/etc/tempo.yaml

# Run Grafana
podman run -d --name grafana \
  -p 3000:3000 \
  -e GF_AUTH_ANONYMOUS_ENABLED=true \
  -e GF_AUTH_ANONYMOUS_ORG_ROLE=Admin \
  grafana/grafana:latest
```

**Option B: Using Podman Pod (Recommended)**

Create `tempo-stack.yaml`:

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: tempo-stack
spec:
  containers:
    - name: tempo
      image: grafana/tempo:latest
      args: ["-config.file=/etc/tempo.yaml"]
      ports:
        - containerPort: 3200
          hostPort: 3200
        - containerPort: 4317
          hostPort: 4317
        - containerPort: 4318
          hostPort: 4318
      volumeMounts:
        - name: tempo-config
          mountPath: /etc/tempo.yaml
          subPath: tempo.yaml

    - name: grafana
      image: grafana/grafana:latest
      env:
        - name: GF_AUTH_ANONYMOUS_ENABLED
          value: "true"
        - name: GF_AUTH_ANONYMOUS_ORG_ROLE
          value: "Admin"
      ports:
        - containerPort: 3000
          hostPort: 3000

  volumes:
    - name: tempo-config
      configMap:
        name: tempo-config
```

**Configure the agent:**

```bash
OTEL_ENABLED=true
OTEL_EXPORTER_TYPE=otlp
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
```

**Configure Grafana Data Source:**

1. Open Grafana at http://localhost:3000
2. Go to **Configuration** → **Data Sources** → **Add data source**
3. Select **Tempo**
4. Set URL to `http://localhost:3200`
5. Click **Save & Test**

**View traces:**

1. Go to **Explore** in Grafana
2. Select **Tempo** data source
3. Use **Search** tab to find traces by service name or trace ID
4. Or use **TraceQL** for advanced queries:
   ```
   { resource.service.name = "insights_agent" }
   ```

### 4. Production with OTLP Collector

For production, use an OpenTelemetry Collector to route traces to your backend:

```yaml
# otel-collector-config.yaml
receivers:
  otlp:
    protocols:
      grpc:
        endpoint: 0.0.0.0:4317
      http:
        endpoint: 0.0.0.0:4318

exporters:
  # Add your backend exporter (e.g., Jaeger, Zipkin, Cloud Trace)
  jaeger:
    endpoint: jaeger:14250
    tls:
      insecure: true

service:
  pipelines:
    traces:
      receivers: [otlp]
      exporters: [jaeger]
```

Run the collector:

```bash
podman run -d --name otel-collector \
  -p 4317:4317 \
  -p 4318:4318 \
  -v ./otel-collector-config.yaml:/etc/otel-collector-config.yaml \
  otel/opentelemetry-collector:latest \
  --config=/etc/otel-collector-config.yaml
```

## Span Attributes

The following attributes are attached to spans:

### Service Attributes
- `service.name`: Agent service name
- `service.version`: Agent version
- `deployment.environment`: `development` or `production`

### Request Attributes (via FastAPI instrumentation)
- `http.method`: HTTP method
- `http.url`: Request URL
- `http.status_code`: Response status code
- `http.route`: FastAPI route pattern

### MCP Attributes (via HTTPX instrumentation)
- `http.url`: MCP server URL
- `http.method`: HTTP method
- `http.status_code`: MCP response status

## Custom Spans

To add custom spans in your code:

```python
from insights_agent.telemetry.setup import get_tracer

tracer = get_tracer(__name__)

with tracer.start_as_current_span("my_operation") as span:
    span.set_attribute("custom.attribute", "value")
    # ... your code
```

## Performance Considerations

- **Sampling**: Use `traceidratio` with 10-20% sampling in production
- **Batch Processing**: Spans are batched before export (default behavior)
- **Overhead**: Typical overhead is <5% with appropriate sampling

## Supported Backends

| Backend | Use Case |
|---------|----------|
| Jaeger | Local development, self-hosted |
| Zipkin | Lightweight tracing |
| Google Cloud Trace | GCP deployments |
| AWS X-Ray | AWS deployments |
| Datadog | Full-stack APM |
| New Relic | Full-stack observability |
| Grafana Tempo | Grafana ecosystem |

## Troubleshooting

### Traces Not Appearing

1. Verify `OTEL_ENABLED=true`
2. Check collector/backend is running
3. Use `OTEL_EXPORTER_TYPE=console` to debug
4. Check agent logs for telemetry initialization messages

### High Latency

1. Reduce sampling rate: `OTEL_TRACES_SAMPLER=traceidratio` with `OTEL_TRACES_SAMPLER_ARG=0.1`
2. Ensure collector is not overloaded
3. Use async batch export (default)

### Missing MCP Spans

HTTPX instrumentation should capture MCP calls automatically. If missing:

1. Verify HTTPX instrumentation is loaded (check startup logs)
2. Ensure MCP transport is using HTTPX (not other clients)
