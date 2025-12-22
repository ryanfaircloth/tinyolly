# TinyOlly v2.1.0

**Release Date:** December 2024

Minor release adding eBPF zero-code tracing demo, Docker Hub images for demo apps, improved documentation, and bug fixes.

---

## Highlights

- **eBPF Zero-Code Tracing Demo** - New demo showcasing OpenTelemetry eBPF Instrumentation (OBI)
- **Docker Hub Images for Demos** - Pre-built eBPF demo images for faster deployment
- **Kubernetes eBPF Demo** - Full Kubernetes deployment with DaemonSet eBPF agent
- **Improved Documentation** - New Demos section with eBPF and AI Agent guides
- **Bug Fixes** - Fixed "Hide TinyOlly" filter for traces and spans

---

## What's New

### eBPF Zero-Code Tracing Demo

New demo showcasing **OpenTelemetry eBPF Instrumentation (OBI)** - automatic trace capture at the Linux kernel level without any code changes.

**Key Features:**
- eBPF agent captures HTTP traces automatically at kernel level
- No tracing SDK in application code - traces come from eBPF
- Logs & Metrics still use OTel SDK (hybrid approach)
- Works with Python, Go, Java, Node.js, Rust, and more

**Docker Deployment:**
```bash
cd docker-demo-ebpf
./01-deploy-ebpf-demo.sh
```

**Kubernetes Deployment:**
```bash
cd k8s-demo-ebpf
./02-deploy.sh
```

**What's Different from SDK Instrumentation:**

| Aspect | SDK | eBPF |
|--------|-----|------|
| Span names | Route names (`GET /hello`) | Generic (`in queue`, `CONNECT`) |
| Span attributes | Rich app context | Network-level only |
| Log correlation | trace_id/span_id present | Empty (no SDK injection) |
| Setup | Code changes required | Deploy eBPF agent only |

See [eBPF Demo Documentation](docs/ebpf.md) for full details.

### Docker Hub Images for eBPF Demo

Pre-built multi-arch images published to Docker Hub:

- `tinyolly/ebpf-frontend:latest` - Frontend with OTel SDK for metrics/logs
- `tinyolly/ebpf-backend:latest` - Pure Flask backend (no OTel SDK)

**Benefits:**
- ~30 second deployment (no local builds needed)
- Multi-architecture: linux/amd64, linux/arm64

**Build & Push Script:**
```bash
cd docker-demo-ebpf
./build-and-push-ebpf-images.sh v2.1.0
```

### Kubernetes eBPF Demo

Full Kubernetes deployment for the eBPF demo:

**Components:**
- `ebpf-frontend.yaml` - Frontend deployment and service
- `ebpf-backend.yaml` - Backend deployment and service
- `ebpf-agent.yaml` - DaemonSet for eBPF agent

**eBPF Agent Configuration:**
```yaml
apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: otel-ebpf-agent
spec:
  template:
    spec:
      hostPID: true
      containers:
      - name: ebpf-agent
        image: docker.io/otel/ebpf-instrument:main
        securityContext:
          privileged: true
        env:
        - name: OTEL_EXPORTER_OTLP_ENDPOINT
          value: "http://otel-collector:4317"
        - name: OTEL_EBPF_OPEN_PORT
          value: "5000"
```

---

## Documentation Updates

### New Demos Section

Added comprehensive documentation for demo applications:

- **[eBPF Zero-Code Tracing](docs/ebpf.md)** - Full guide on OBI, differences from SDK instrumentation, configuration, and troubleshooting
- **[AI Agent with Ollama](docs/ai-agent.md)** - GenAI observability documentation with Ollama integration

### Updated mkdocs Navigation

```yaml
- Demos:
    - eBPF Zero-Code Tracing: ebpf.md
    - AI Agent with Ollama: ai-agent.md
```

### README Updates

- Added deployment time notes for eBPF demo
- Added Docker Hub image references for Kubernetes eBPF demo
- Updated quick start sections with clearer instructions

---

## Bug Fixes

### Hide TinyOlly Filter for Traces and Spans

Fixed the "Hide TinyOlly" button not filtering traces and spans correctly.

**Problem:** The filter was checking for `root_service` field, but the API returns `service_name`.

**Fix:** Updated `filterTinyOllyTrace()` in `filter.js`:
```javascript
export function filterTinyOllyTrace(trace) {
    if (!hideTinyOlly) return true;
    // API returns service_name field for traces
    const serviceName = trace.service_name || trace.serviceName ||
                        trace.root_service || trace.rootService;
    return serviceName !== 'tinyolly-ui';
}
```

### Hide TinyOlly Filter for Metrics

Fixed the "Hide TinyOlly" button not filtering metrics correctly.

**Problem:** The metrics list API didn't include service information, so the filter couldn't identify which metrics came from tinyolly-ui.

**Fix:**
1. Added `services` field to metrics list API response (list of service names emitting each metric)
2. Updated `filterTinyOllyMetric()` to check the services array
3. Fixed `04-rebuild-ui.sh` to use local compose file for building

---

## New Files

### docker-demo-ebpf/
- `docker-compose.yml` - eBPF demo with Docker Hub images
- `build-and-push-ebpf-images.sh` - Multi-arch build and push script
- `01-deploy-ebpf-demo.sh` - Deploy script
- `02-cleanup.sh` - Cleanup script

### k8s-demo-ebpf/
- `ebpf-frontend.yaml` - Frontend deployment
- `ebpf-backend.yaml` - Backend deployment
- `ebpf-agent.yaml` - eBPF agent DaemonSet
- `01-build-images.sh` - Local image build (optional)
- `02-deploy.sh` - Deploy script
- `03-cleanup.sh` - Cleanup script

### Documentation
- `docs/ebpf.md` - eBPF demo documentation
- `docs/ai-agent.md` - AI agent demo documentation

---

## Upgrade Instructions

### From v2.0.0

TinyOlly v2.1.0 is **100% backward compatible**. No breaking changes.

**Upgrade Steps:**
```bash
# Pull latest changes
git pull origin main

# Restart Docker deployment
cd docker
./02-stop-core.sh
./01-start-core.sh

# Try the new eBPF demo
cd ../docker-demo-ebpf
./01-deploy-ebpf-demo.sh
```

---

## Quick Start - eBPF Demo

```bash
# Clone repository
git clone https://github.com/tinyolly/tinyolly
cd tinyolly
git checkout v2.1.0

# Start TinyOlly core
cd docker
./01-start-core.sh

# Deploy eBPF demo
cd ../docker-demo-ebpf
./01-deploy-ebpf-demo.sh

# Access the UI
# http://localhost:5005

# View traces - notice generic span names from eBPF
# View logs - notice empty trace_id/span_id
# View metrics - working normally via SDK
```

---

## Additional Resources

- [Documentation](https://tinyolly.github.io/tinyolly/)
- [eBPF Demo Guide](docs/ebpf.md)
- [AI Agent Demo Guide](docs/ai-agent.md)
- [GitHub Repository](https://github.com/tinyolly/tinyolly)

---

**Built for the OpenTelemetry community**
