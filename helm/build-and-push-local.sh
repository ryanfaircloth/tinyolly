#!/usr/bin/env bash
# Build and push containers + Helm chart for local development
# This script:
#   1. Builds container images (python-base, UI, OTLP receiver, OpAMP server)
#   2. Pushes them to local registry
#   3. Packages and pushes Helm chart to OCI registry
# Usage: ./build-and-push-local.sh [version-tag]
# Example: ./build-and-push-local.sh v2.1.8-test

set -euo pipefail

VERSION=${1:-"local-$(date +%s)"}
REGISTRY="registry.tinyolly.test:49443"
CHART_REGISTRY="${REGISTRY}/tinyolly/charts"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "==============================================="
echo "Building TinyOlly: Containers + Helm Chart"
echo "==============================================="
echo "Version tag: $VERSION"
echo "Container registry: $REGISTRY"
echo "Chart registry: oci://$CHART_REGISTRY"
echo ""

# Detect container runtime (podman or docker)
if command -v podman &> /dev/null; then
    CONTAINER_CMD="podman"
    PUSH_FLAGS="--tls-verify=false"
    echo "Using: podman (TLS verify disabled for local registry)"
elif command -v docker &> /dev/null; then
    CONTAINER_CMD="docker"
    PUSH_FLAGS=""
    echo "Using: docker"
    echo "Note: Ensure Docker daemon has $REGISTRY in insecure-registries"
else
    echo "❌ Error: Neither podman nor docker found"
    exit 1
fi
echo ""

# ==========================================
# PART 1: Build and Push Container Images
# ==========================================

echo "📦 PART 1: Building Container Images"
echo "=========================================="
echo ""

# Navigate to docker directory (build context)
cd "$SCRIPT_DIR/../docker"

echo "Step 1/4: Building python-base (includes tinyolly-common)"
echo "-----------------------------------------------------------"
$CONTAINER_CMD build \
  -f dockerfiles/Dockerfile.tinyolly-python-base \
  -t tinyolly/python-base:latest \
  -t tinyolly/python-base:$VERSION \
  .
echo "✓ Base image built"
echo ""

echo "Step 2/4: Building UI (uses local python-base)"
echo "-----------------------------------------------------------"
$CONTAINER_CMD build \
  -f dockerfiles/Dockerfile.tinyolly-ui \
  --build-arg APP_DIR=tinyolly-ui \
  -t tinyolly/ui:latest \
  -t tinyolly/ui:$VERSION \
  -t $REGISTRY/tinyolly/ui:latest \
  -t $REGISTRY/tinyolly/ui:$VERSION \
  .
echo "✓ UI image built"
echo ""

echo "Step 3/4: Building OTLP Receiver (uses local python-base)"
echo "-----------------------------------------------------------"
$CONTAINER_CMD build \
  -f dockerfiles/Dockerfile.tinyolly-otlp-receiver \
  --build-arg APP_DIR=tinyolly-otlp-receiver \
  -t tinyolly/otlp-receiver:latest \
  -t tinyolly/otlp-receiver:$VERSION \
  -t $REGISTRY/tinyolly/otlp-receiver:latest \
  -t $REGISTRY/tinyolly/otlp-receiver:$VERSION \
  .
echo "✓ OTLP Receiver image built"
echo ""

echo "Step 4/4: Building OpAMP Server"
echo "-----------------------------------------------------------"
$CONTAINER_CMD build \
  -f dockerfiles/Dockerfile.tinyolly-opamp-server \
  --build-arg APP_DIR=tinyolly-opamp-server \
  -t tinyolly/opamp-server:latest \
  -t tinyolly/opamp-server:$VERSION \
  -t $REGISTRY/tinyolly/opamp-server:latest \
  -t $REGISTRY/tinyolly/opamp-server:$VERSION \
  .
echo "✓ OpAMP Server image built"
echo ""

echo "📤 Pushing Container Images to Registry"
echo "=========================================="
echo ""

echo "Pushing UI..."
$CONTAINER_CMD push $PUSH_FLAGS $REGISTRY/tinyolly/ui:latest
$CONTAINER_CMD push $PUSH_FLAGS $REGISTRY/tinyolly/ui:$VERSION
echo "✓ UI pushed"
echo ""

echo "Pushing OTLP Receiver..."
$CONTAINER_CMD push $PUSH_FLAGS $REGISTRY/tinyolly/otlp-receiver:latest
$CONTAINER_CMD push $PUSH_FLAGS $REGISTRY/tinyolly/otlp-receiver:$VERSION
echo "✓ OTLP Receiver pushed"
echo ""

echo "Pushing OpAMP Server..."
$CONTAINER_CMD push $PUSH_FLAGS $REGISTRY/tinyolly/opamp-server:latest
$CONTAINER_CMD push $PUSH_FLAGS $REGISTRY/tinyolly/opamp-server:$VERSION
echo "✓ OpAMP Server pushed"
echo ""

# ==========================================
# PART 2: Package and Push Helm Chart
# ==========================================

echo "📦 PART 2: Packaging Helm Chart"
echo "=========================================="
echo ""

cd "$SCRIPT_DIR"

# Update Chart.yaml with the new version
CHART_DIR="$SCRIPT_DIR/tinyolly"
CHART_YAML="$CHART_DIR/Chart.yaml"

# Extract current chart version
CURRENT_CHART_VERSION=$(grep "^version:" "$CHART_YAML" | awk '{print $2}')
echo "Current chart version: $CURRENT_CHART_VERSION"

# Update values.yaml to use the new image tags
VALUES_YAML="$CHART_DIR/values.yaml"
echo "Updating image tags in values.yaml to: $VERSION"

# Create a temporary values file for local development
cat > "$SCRIPT_DIR/values-local-dev.yaml" <<EOF
# Auto-generated local development values
# Generated: $(date)
# Version: $VERSION

ui:
  image:
    repository: $REGISTRY/tinyolly/ui
    tag: $VERSION

opampServer:
  image:
    repository: $REGISTRY/tinyolly/opamp-server
    tag: $VERSION

otlpReceiver:
  image:
    repository: $REGISTRY/tinyolly/otlp-receiver
    tag: $VERSION
EOF

echo "✓ Created values-local-dev.yaml with updated image tags"
echo ""

# Lint the chart
echo "🔍 Linting Helm chart..."
helm lint "$CHART_DIR"
echo "✓ Chart linted successfully"
echo ""

# Package the chart
echo "📦 Packaging chart..."
helm package "$CHART_DIR" -d "$SCRIPT_DIR"
CHART_PACKAGE="$SCRIPT_DIR/tinyolly-${CURRENT_CHART_VERSION}.tgz"
echo "✓ Chart packaged: $(basename "$CHART_PACKAGE")"
echo ""

# Push to OCI registry
echo "📤 Pushing Helm chart to OCI registry..."
echo "   Registry: oci://$CHART_REGISTRY"
echo ""

if [[ "$CONTAINER_CMD" == "podman" ]]; then
    # Helm uses the container credential helper, so we need to login
    echo "🔐 Logging into registry (required for Helm with podman)..."
    # Check if already logged in
    if ! helm registry login "$REGISTRY" --help &>/dev/null 2>&1; then
        echo "⚠️  Note: You may need to run: helm registry login $REGISTRY"
    fi
fi

# Push the chart (skip if helm can't handle insecure registries easily)
if helm push "$CHART_PACKAGE" "oci://$CHART_REGISTRY" 2>/dev/null; then
    echo "✓ Chart pushed successfully"
else
    echo "⚠️  Warning: Chart push may have failed (this is common with local registries)"
    echo "   You can still install from the local package: $CHART_PACKAGE"
fi
echo ""

# ==========================================
# Summary
# ==========================================

echo "✅ BUILD COMPLETE"
echo "=========================================="
echo ""
echo "Container Images:"
echo "  • $REGISTRY/tinyolly/ui:$VERSION"
echo "  • $REGISTRY/tinyolly/opamp-server:$VERSION"
echo "  • $REGISTRY/tinyolly/otlp-receiver:$VERSION"
echo ""
echo "Helm Chart:"
echo "  • Package: $(basename "$CHART_PACKAGE")"
echo "  • Version: $CURRENT_CHART_VERSION"
echo ""
echo "📋 Next Steps:"
echo ""
echo "  Install with Helm (using local values):"
echo "    cd helm"
echo "    helm install tinyolly ./tinyolly \\"
echo "      --namespace tinyolly \\"
echo "      --create-namespace \\"
echo "      --values values-local-dev.yaml"
echo ""
echo "  Or upgrade existing installation:"
echo "    helm upgrade tinyolly ./tinyolly \\"
echo "      --namespace tinyolly \\"
echo "      --values values-local-dev.yaml"
echo ""
echo "  Deploy to ArgoCD (recommended):"
echo "    ./deploy-to-argocd.sh"
echo ""
echo "  Deploy specific image version with kubectl:"
echo "    kubectl set image deployment/tinyolly-ui \\"
echo "      tinyolly-ui=$REGISTRY/tinyolly/ui:$VERSION -n tinyolly"
echo ""

# Optionally deploy to ArgoCD
if [ "${DEPLOY_TO_ARGOCD:-}" = "true" ]; then
    echo "🚀 Deploying to ArgoCD..."
    "$SCRIPT_DIR/deploy-to-argocd.sh"
fi
