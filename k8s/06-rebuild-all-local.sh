#!/bin/bash
set -e

# Rebuild ALL TinyOlly images for local testing with custom registry
# Builds: python-base, UI, OTLP receiver, OpAMP server
# Pushes to: registry.tinyolly.test:49443 (TLS, untrusted)
# Usage: ./06-rebuild-all-local.sh [version-tag]
# Example: ./06-rebuild-all-local.sh v2.1.8-test

VERSION=${1:-"local-$(date +%s)"}
REGISTRY="registry.tinyolly.test:49443"

echo "==============================================="
echo "Rebuilding ALL TinyOlly Components"
echo "==============================================="
echo "Version tag: $VERSION"
echo "Registry: $REGISTRY (TLS, skip verify)"
echo ""

# Detect container runtime (podman or docker)
if command -v podman &> /dev/null; then
    CONTAINER_CMD="podman"
    PUSH_FLAGS="--tls-verify=false"
    echo "Using: podman"
elif command -v docker &> /dev/null; then
    CONTAINER_CMD="docker"
    PUSH_FLAGS=""
    echo "Using: docker"
    echo "Note: Ensure Docker daemon has registry.tinyolly.test:49443 in insecure-registries"
else
    echo "Error: Neither podman nor docker found"
    exit 1
fi
echo ""

# Navigate to docker directory (build context)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/../docker"

echo "Step 1/7: Building python-base (includes tinyolly-common)"
echo "---------------------------------------------------"
$CONTAINER_CMD build \
  -f dockerfiles/Dockerfile.tinyolly-python-base \
  -t tinyolly/python-base:latest \
  -t tinyolly/python-base:$VERSION \
  .
echo "✓ Base image built with local storage.py changes"
echo ""

echo "Step 2/7: Building UI (uses local python-base)"
echo "---------------------------------------------------"
$CONTAINER_CMD build \
  -f dockerfiles/Dockerfile.tinyolly-ui \
  --build-arg APP_DIR=tinyolly-ui \
  -t $REGISTRY/tinyolly/ui:$VERSION \
  -t $REGISTRY/tinyolly/ui:latest \
  .
echo "✓ UI image built"
echo ""

echo "Step 3/7: Building OTLP Receiver"
echo "---------------------------------------------------"
$CONTAINER_CMD build \
  -f dockerfiles/Dockerfile.tinyolly-otlp-receiver \
  --build-arg APP_DIR=tinyolly-otlp-receiver \
  -t $REGISTRY/tinyolly/otlp-receiver:$VERSION \
  -t $REGISTRY/tinyolly/otlp-receiver:latest \
  .
echo "✓ OTLP Receiver image built"
echo ""

echo "Step 4/7: Building OpAMP Server"
echo "---------------------------------------------------"
$CONTAINER_CMD build \
  -f dockerfiles/Dockerfile.tinyolly-opamp-server \
  -t $REGISTRY/tinyolly/opamp-server:$VERSION \
  -t $REGISTRY/tinyolly/opamp-server:latest \
  .
echo "✓ OpAMP Server image built"
echo ""

echo "Step 5/7: Testing registry accessibility"
echo "---------------------------------------------------"
if ! curl -sfk https://registry.tinyolly.test:49443/v2/_catalog > /dev/null 2>&1; then
    echo "⚠ Warning: Registry at registry.tinyolly.test:49443 may not be accessible"
    echo "Attempting to push anyway..."
else
    echo "✓ Registry is accessible"
fi
echo ""

echo "Step 6/7: Pushing images to $REGISTRY"
echo "---------------------------------------------------"
IMAGES=(
    "$REGISTRY/tinyolly/ui:$VERSION"
    "$REGISTRY/tinyolly/ui:latest"
    "$REGISTRY/tinyolly/otlp-receiver:$VERSION"
    "$REGISTRY/tinyolly/otlp-receiver:latest"
    "$REGISTRY/tinyolly/opamp-server:$VERSION"
    "$REGISTRY/tinyolly/opamp-server:latest"
)

FAILED=0
for IMAGE in "${IMAGES[@]}"; do
    echo "Pushing $IMAGE..."
    if [ -n "$PUSH_FLAGS" ]; then
        if $CONTAINER_CMD push $PUSH_FLAGS $IMAGE; then
            echo "✓ Pushed $IMAGE"
        else
            echo "✗ Failed to push $IMAGE"
            FAILED=$((FAILED + 1))
        fi
    else
        if $CONTAINER_CMD push $IMAGE; then
            echo "✓ Pushed $IMAGE"
        else
            echo "✗ Failed to push $IMAGE"
            FAILED=$((FAILED + 1))
        fi
    fi
done
echo ""

if [ $FAILED -gt 0 ]; then
    echo "✗ $FAILED image(s) failed to push"
    echo ""
    echo "Troubleshooting:"
    echo "1. Verify registry is running and accessible:"
    echo "   curl -k https://registry.tinyolly.test:49443/v2/_catalog"
    echo ""
    echo "2. For Docker, add to /etc/docker/daemon.json:"
    echo "   {\"insecure-registries\": [\"registry.tinyolly.test:49443\"]}"
    echo ""
    echo "3. For podman, TLS verification is skipped via --tls-verify=false"
    exit 1
fi

echo "==============================================="
echo "✓ Build & Push Complete!"
echo "==============================================="
echo "Images pushed to: $REGISTRY"
echo "  - tinyolly/ui:$VERSION"
echo "  - tinyolly/otlp-receiver:$VERSION"
echo "  - tinyolly/opamp-server:$VERSION"
echo ""
echo "Deploy with:"
echo "  ./07-deploy-local-images.sh $VERSION"
echo ""
echo "Or manually:"
echo "  kubectl set image deployment/tinyolly-ui tinyolly-ui=$REGISTRY/tinyolly/ui:$VERSION -n tinyolly"
echo "  kubectl set image deployment/tinyolly-otlp-receiver tinyolly-otlp-receiver=$REGISTRY/tinyolly/otlp-receiver:$VERSION -n tinyolly"
echo "  kubectl set image deployment/tinyolly-opamp-server tinyolly-opamp-server=$REGISTRY/tinyolly/opamp-server:$VERSION -n tinyolly"
echo ""
echo "Clear Redis cache after deployment:"
echo "  kubectl exec -n tinyolly deployment/tinyolly-redis -- redis-cli -p 6379 FLUSHDB"
