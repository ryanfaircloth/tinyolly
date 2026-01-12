#!/bin/bash
set -e

# Deploy locally built images to Kubernetes cluster
# Updates deployments to use images from registry.tinyolly.test:49443
# Usage: ./07-deploy-local-images.sh [version-tag]
# Example: ./07-deploy-local-images.sh v2.1.8-test

VERSION=${1:-"latest"}
REGISTRY_EXTERNAL="registry.tinyolly.test:49443"
REGISTRY_INTERNAL="docker-registry.registry.svc.cluster.local:5000"
NAMESPACE="tinyolly"

echo "==============================================="
echo "Deploying TinyOlly from Local Registry"
echo "==============================================="
echo "Version: $VERSION"
echo "External registry: $REGISTRY_EXTERNAL (for push)"
echo "Internal registry: $REGISTRY_INTERNAL (for deployment)"
echo "Namespace: $NAMESPACE"
echo ""

# Check if namespace exists
if ! kubectl get namespace $NAMESPACE &> /dev/null; then
    echo "Creating namespace: $NAMESPACE"
    kubectl create namespace $NAMESPACE
    echo ""
fi

# Update image pull policy to allow insecure registry
echo "Step 1/4: Updating image references"
echo "---------------------------------------------------"

DEPLOYMENTS=(
    "tinyolly-ui:$REGISTRY_INTERNAL/tinyolly/ui:$VERSION"
    "tinyolly-otlp-receiver:$REGISTRY_INTERNAL/tinyolly/otlp-receiver:$VERSION"
    "tinyolly-opamp-server:$REGISTRY_INTERNAL/tinyolly/opamp-server:$VERSION"
)

for DEPLOYMENT_IMAGE in "${DEPLOYMENTS[@]}"; do
    DEPLOYMENT_NAME="${DEPLOYMENT_IMAGE%%:*}"
    IMAGE="${DEPLOYMENT_IMAGE#*:}"
    
    echo "Updating $DEPLOYMENT_NAME to use $IMAGE..."
    
    if kubectl get deployment $DEPLOYMENT_NAME -n $NAMESPACE &> /dev/null; then
        kubectl set image deployment/$DEPLOYMENT_NAME $DEPLOYMENT_NAME=$IMAGE -n $NAMESPACE
        echo "✓ Updated $DEPLOYMENT_NAME"
    else
        echo "⚠ Deployment $DEPLOYMENT_NAME not found, skipping..."
    fi
done
echo ""

echo "Step 2/4: Waiting for rollouts to complete"
echo "---------------------------------------------------"
for DEPLOYMENT_IMAGE in "${DEPLOYMENTS[@]}"; do
    DEPLOYMENT_NAME="${DEPLOYMENT_IMAGE%%:*}"
    
    if kubectl get deployment $DEPLOYMENT_NAME -n $NAMESPACE &> /dev/null; then
        echo "Waiting for $DEPLOYMENT_NAME..."
        kubectl rollout status deployment/$DEPLOYMENT_NAME -n $NAMESPACE --timeout=120s
    fi
done
echo ""

echo "Step 3/4: Verifying pod status"
echo "---------------------------------------------------"
kubectl get pods -n $NAMESPACE -o wide
echo ""

echo "Step 4/4: Checking image sources"
echo "---------------------------------------------------"
for DEPLOYMENT_IMAGE in "${DEPLOYMENTS[@]}"; do
    DEPLOYMENT_NAME="${DEPLOYMENT_IMAGE%%:*}"
    
    if kubectl get deployment $DEPLOYMENT_NAME -n $NAMESPACE &> /dev/null; then
        CURRENT_IMAGE=$(kubectl get deployment $DEPLOYMENT_NAME -n $NAMESPACE -o jsonpath='{.spec.template.spec.containers[0].image}')
        echo "$DEPLOYMENT_NAME: $CURRENT_IMAGE"
    fi
done
echo ""

echo "==============================================="
echo "✓ Deployment Complete!"
echo "==============================================="
echo ""
echo "Services:"
echo "  UI: http://localhost:5002"
echo "  OTLP: http://localhost:4343"
echo "  OpAMP: http://localhost:4320"
echo ""
echo "Useful commands:"
echo "  kubectl logs -f deployment/tinyolly-ui -n $NAMESPACE"
echo "  kubectl exec -n $NAMESPACE deployment/tinyolly-redis -- redis-cli -p 6379 FLUSHDB"
echo ""
echo "Note: If ImagePullBackOff occurs, ensure cluster can access registry.tinyolly.test:49443"
echo "For Kind clusters, add registry to /etc/containerd/config.toml on Kind nodes"
