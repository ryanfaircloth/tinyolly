#!/bin/bash
set -e

# Configure Kind cluster to trust local registry
# Adds registry.tinyolly.test:49443 to containerd config with TLS skip verify
# Usage: ./08-configure-kind-registry.sh [cluster-name]
# Example: ./08-configure-kind-registry.sh kind

CLUSTER_NAME=${1:-"kind"}

echo "==============================================="
echo "Configuring Kind Registry Access"
echo "==============================================="
echo "Cluster: $CLUSTER_NAME"
echo "Registry: registry.tinyolly.test:49443"
echo ""

# Get Kind control plane node
CONTROL_PLANE=$(kubectl get nodes --selector=node-role.kubernetes.io/control-plane -o jsonpath='{.items[0].metadata.name}')
if [ -z "$CONTROL_PLANE" ]; then
    echo "✗ Could not find Kind control plane node"
    echo "Is the cluster running?"
    exit 1
fi

echo "Control plane node: $CONTROL_PLANE"
echo ""

echo "Step 1/3: Creating containerd registry configuration"
echo "---------------------------------------------------"

# Create containerd config patch
CONTAINERD_CONFIG=$(cat <<'EOF'
[plugins."io.containerd.grpc.v1.cri".registry]
  [plugins."io.containerd.grpc.v1.cri".registry.mirrors]
    [plugins."io.containerd.grpc.v1.cri".registry.mirrors."registry.tinyolly.test:49443"]
      endpoint = ["https://registry.tinyolly.test:49443"]
  [plugins."io.containerd.grpc.v1.cri".registry.configs]
    [plugins."io.containerd.grpc.v1.cri".registry.configs."registry.tinyolly.test:49443".tls]
      insecure_skip_verify = true
EOF
)

# Write config to Kind node
docker exec $CONTROL_PLANE mkdir -p /etc/containerd/certs.d/registry.tinyolly.test:49443
docker exec $CONTROL_PLANE sh -c "cat > /etc/containerd/certs.d/registry.tinyolly.test:49443/hosts.toml <<'EOF'
server = \"https://registry.tinyolly.test:49443\"

[host.\"https://registry.tinyolly.test:49443\"]
  capabilities = [\"pull\", \"resolve\"]
  skip_verify = true
EOF"

echo "✓ Registry configuration created"
echo ""

echo "Step 2/3: Restarting containerd"
echo "---------------------------------------------------"
docker exec $CONTROL_PLANE systemctl restart containerd
sleep 5
echo "✓ containerd restarted"
echo ""

echo "Step 3/3: Verifying configuration"
echo "---------------------------------------------------"
if docker exec $CONTROL_PLANE crictl pull --creds '' registry.tinyolly.test:49443/tinyolly/ui:latest 2>&1 | grep -q "Pulling image\|Image is up to date\|already present"; then
    echo "✓ Registry is accessible from Kind node"
else
    echo "⚠ Could not verify registry access"
    echo "This may be normal if no images are pushed yet"
fi
echo ""

echo "==============================================="
echo "✓ Configuration Complete!"
echo "==============================================="
echo ""
echo "Kind cluster can now pull images from:"
echo "  registry.tinyolly.test:49443"
echo ""
echo "Next steps:"
echo "  1. Build and push images: ./06-rebuild-all-local.sh v1.0.0"
echo "  2. Deploy to cluster: ./07-deploy-local-images.sh v1.0.0"
echo ""
echo "Note: You may need to configure other worker nodes if using multi-node Kind cluster"
