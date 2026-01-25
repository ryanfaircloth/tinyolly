#!/bin/bash
# Verification script for PostgreSQL integration tests setup
# Run this after cluster is fully deployed

set -e

echo "========================================"
echo "PostgreSQL Integration Tests Verification"
echo "========================================"
echo ""

# 1. Check cluster is up
echo "1. Checking cluster status..."
if ! kubectl get nodes &>/dev/null; then
    echo "❌ Cluster is not accessible"
    exit 1
fi
echo "✓ Cluster accessible"
echo ""

# 2. Check ollyscale namespace exists
echo "2. Checking ollyscale namespace..."
if ! kubectl get ns ollyscale &>/dev/null; then
    echo "❌ ollyscale namespace doesn't exist - run 'make deploy'"
    exit 1
fi
echo "✓ ollyscale namespace exists"
echo ""

# 3. Check PostgreSQL pods are running
echo "3. Checking PostgreSQL cluster pods..."
kubectl get pods -n ollyscale -l cnpg.io/cluster=ollyscale-db --no-headers
if [ $? -ne 0 ]; then
    echo "❌ PostgreSQL pods not found"
    exit 1
fi
echo "✓ PostgreSQL cluster pods found"
echo ""

# 4. Check Gateway has kafka-listener
echo "4. Checking Gateway kafka-listener configuration..."
KAFKA_PORT=$(kubectl get gateway cluster-gateway -n envoy-gateway-system -o jsonpath='{.spec.listeners[?(@.name=="kafka-listener")].port}' 2>/dev/null)
if [ "$KAFKA_PORT" != "9094" ]; then
    echo "❌ kafka-listener not configured on port 9094 (got: $KAFKA_PORT)"
    exit 1
fi
echo "✓ kafka-listener configured on port 9094"
echo ""

# 5. Check TLSRoute exists
echo "5. Checking PostgreSQL TLSRoute..."
if ! kubectl get tlsroute ollyscale-db-tls -n ollyscale &>/dev/null; then
    echo "❌ TLSRoute ollyscale-db-tls not found - check ArgoCD application"
    exit 1
fi
echo "✓ TLSRoute ollyscale-db-tls exists"
kubectl get tlsroute ollyscale-db-tls -n ollyscale -o jsonpath='{.spec.hostnames[0]}' | xargs echo "  Hostname:"
echo ""

# 6. Get PostgreSQL password from secret
echo "6. Fetching PostgreSQL password from secret..."
SECRET_NAME=$(kubectl get secrets -n ollyscale -o name | grep ollyscale-db | grep -v replication | grep -v ca | grep -v server | head -1)
if [ -z "$SECRET_NAME" ]; then
    echo "❌ Could not find PostgreSQL secret"
    exit 1
fi
echo "  Secret: $SECRET_NAME"
PASSWORD=$(kubectl get $SECRET_NAME -n ollyscale -o jsonpath='{.data.password}' | base64 -d)
echo "✓ Password retrieved"
echo ""

# 7. Show connection string for tests
echo "7. PostgreSQL connection details for tests:"
echo "  Host: ollyscale-db.ollyscale.test"
echo "  Port: 9094 (via kafka-listener)"
echo "  User: ollyscale"
echo "  Database: ollyscale"
echo "  Password: $PASSWORD"
echo "  SSL Mode: require"
echo ""
echo "Connection string:"
echo "  postgresql+asyncpg://ollyscale:$PASSWORD@ollyscale-db.ollyscale.test:9094/ollyscale?sslmode=require"
echo ""

# 8. Run integration tests
echo "========================================"
echo "Running Integration Tests"
echo "========================================"
echo ""

cd "$(dirname "$0")/apps/frontend"

echo "Setting POSTGRES_PASSWORD environment variable..."
export POSTGRES_PASSWORD="$PASSWORD"

echo "Running test_logs_metrics_storage.py..."
poetry run pytest tests/test_logs_metrics_storage.py -xvs

echo ""
echo "========================================"
echo "✓ All verifications and tests passed!"
echo "========================================"
