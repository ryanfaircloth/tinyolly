# Obsolete Scripts Analysis

Generated: 2026-01-12

## Summary

With the adoption of the **Terraform + ArgoCD + Helm** workflow (via `helm/build-and-push-local.sh`), several legacy scripts and workflows are no longer needed.

## ✅ KEEP - Still Valid Use Cases

### Docker Compose (Local Development)
- `docker/01-start-core-local.sh` - **KEEP**: Quick Docker Compose testing
- `docker/01-start-core.sh` - **KEEP**: Pull & run from GHCR
- `docker/02-stop-core.sh` - **KEEP**: Stop Docker Compose
- `docker/04-rebuild-ui.sh` - **KEEP**: Fast UI iteration for Docker Compose
- `docker/03-force-rebuild.sh` - **KEEP**: Clean rebuild for Docker Compose

**Rationale**: Docker Compose workflow is still valid for:
- Quick local testing without Kubernetes
- Demos and quickstart environments
- CI/CD integration testing

### GitHub Container Registry (GHCR) Builds
- `build/dockerhub/*` - **KEEP**: Used for CI/CD and production releases to GHCR
  - `02-build-*.sh` - Build production images
  - `03-push-*.sh` - Push to GHCR

**Rationale**: These are for **production releases** and **GitHub Actions CI/CD**, not local development.

## ❌ OBSOLETE - Can Be Removed

### Minikube Build Scripts
- `build/local/build-core-minikube.sh` - **OBSOLETE**
- `build/local/build-demo-minikube.sh` - **OBSOLETE**
- `build/local/build-ebpf-demo-minikube.sh` - **OBSOLETE**

**Reason**: Replaced by `helm/build-and-push-local.sh` which:
- Builds images for KIND cluster (not Minikube)
- Pushes to local OCI registry (`registry.tinyolly.test:49443`)
- Packages and pushes Helm chart to OCI registry
- Generates `values-local-dev.yaml` with correct internal registry DNS
- Integrates with ArgoCD deployment

**Migration Path**:
```bash
# OLD (Minikube)
cd build/local
./build-core-minikube.sh

# NEW (KIND + Helm + ArgoCD)
cd helm
./build-and-push-local.sh v2.1.x-test
```

### Old K8s Demo Scripts
- `k8s-demo/02-deploy.sh` - **OBSOLETE**
- `k8s-demo/03-cleanup.sh` - **OBSOLETE**
- `k8s-demo/04-rebuild-demo.sh` - **OBSOLETE**
- `k8s-demo/generate-traffic.sh` - **OBSOLETE**
- `k8s-otel-demo/01-deploy-otel-demo-helm.sh` - **OBSOLETE**
- `k8s-otel-demo/02-cleanup-otel-demo-helm.sh` - **OBSOLETE**

**Reason**: Replaced by unified `helm/tinyolly-demos` Helm chart which:
- Deploys both custom demo and OTel Demo via single chart
- Integrates with ArgoCD for GitOps
- Supports HTTPRoutes for ingress
- Provides enable/disable flags per demo
- Includes local registry support

**Migration Path**:
```bash
# OLD (Custom Demo)
cd k8s-demo
./02-deploy.sh

# NEW (Helm)
cd helm
./build-and-push-local.sh v2.1.x-demo  # Build images
# Then deploy via ArgoCD or directly:
helm install tinyolly-demos ./tinyolly-demos \
  --namespace tinyolly-demos --create-namespace

# Or via Terraform
cd .kind
terraform apply -var="custom_demo_enabled=true"
```

**Migration Path for OTel Demo**:
```bash
# OLD (OTel Demo)
cd k8s-otel-demo
./01-deploy-otel-demo-helm.sh

# NEW (Helm)
helm install tinyolly-demos helm/tinyolly-demos \
  --set customDemo.enabled=false \
  --set otelDemo.enabled=true

# Or via Terraform
cd .kind
terraform apply -var="otel_demo_enabled=true" -var="custom_demo_enabled=false"
```

### Old K8s Core Scripts
- `k8s/05-rebuild-local-changes.sh` - **OBSOLETE**
- `k8s/06-rebuild-all-local.sh` - **OBSOLETE**
- `k8s/07-deploy-local-images.sh` - **OBSOLETE**

**Reason**: Replaced by `helm/build-and-push-local.sh`
cd helm
./build-and-push-local.sh v2.1.x-description
cd ../.kind
terraform apply -replace='kubectl_manifest.observability_applications["observability/tinyolly.yaml"]' -auto-approve
```

### Directory to Remove
```bash
rm -rf build/local/
```

## 📝 Documentation Updates Needed

### Files to Update

1. **`build/README.md`**
   - Remove all references to Minikube builds
   - Remove "Quick Start - Local (Minikube)" section
   - Add pointer to `helm/build-and-push-local.sh` for Kubernetes development

2. **`README.md`**
   - Update line 29: Change "Minikube" to "KIND"
   - Remove line 216: `minikube tunnel` reference
   - Update line 235: Change `./build/local/build-demo-minikube.sh` to `helm/build-and-push-local.sh`

3. **`k8s-ai-agent-demo/README.md`**
   - Update line 7: Change "minikube, kind, or cloud provider" to "KIND or cloud provider"

## Current Recommended Workflows

### Local Kubernetes Development (KIND)
```bash
# Bootstrap cluster
make up

# Build and deploy TinyOlly
cd helm
./build-and-push-local.sh v2.1.x-feature

# Update ArgoCD Application
cd ../.kind
terraform apply -replace='kubectl_manifest.observability_applications["observability/tinyolly.yaml"]' -auto-approve
```

### Docker Compose Development
```bash
cd docker

# Quick start (pull from GHCR)
./01-start-core.sh

# Local development
./01-start-core-local.sh

# Rebuild UI only
./04-rebuild-ui.sh

# Stop
./02-stop-core.sh
```

### Production Releases (GHCR)
```bash
cd build/dockerhub

# Build and push
export CONTAINER_REGISTRY=ghcr.io/ryanfaircloth
./02-build-all.sh v2.1.0
./03-push-all.sh v2.1.0
```

## Implementation Plan

1. ✅ Remove checked-in .tgz files (completed)
2. ✅ Clean up .gitignore duplicates (completed)
3. ⏳ Remove `build/local/` directory
4. ⏳ Update documentation (README.md, build/README.md, k8s-ai-agent-demo/README.md)
5. ⏳ Commit and push changes
