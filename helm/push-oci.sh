#!/usr/bin/env bash
# Push TinyOlly Helm Chart to OCI Registry

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Check if registry URL is provided
if [ $# -eq 0 ]; then
    echo "❌ Error: Registry URL is required"
    echo ""
    echo "Usage: $0 <registry-url> [chart-version]"
    echo ""
    echo "Examples:"
    echo "  $0 ghcr.io/tinyolly/charts"
    echo "  $0 ghcr.io/tinyolly/charts 0.1.0"
    echo "  $0 registry.tinyolly.test:49443/tinyolly/charts"
    exit 1
fi

REGISTRY_URL="$1"
CHART_VERSION="${2:-}"

# Find the chart package
if [ -n "${CHART_VERSION}" ]; then
    CHART_PACKAGE="${SCRIPT_DIR}/tinyolly-${CHART_VERSION}.tgz"
else
    # Get the latest packaged chart
    CHART_PACKAGE=$(ls -t "${SCRIPT_DIR}"/tinyolly-*.tgz 2>/dev/null | head -1)
fi

if [ ! -f "${CHART_PACKAGE}" ]; then
    echo "❌ Error: Chart package not found!"
    echo ""
    echo "Please run './package.sh' first to create the chart package."
    exit 1
fi

echo "🚀 Pushing TinyOlly Helm Chart to OCI Registry..."
echo "   Registry: ${REGISTRY_URL}"
echo "   Package:  $(basename "${CHART_PACKAGE}")"
echo ""

# Check if already logged in
if ! helm registry login "${REGISTRY_URL%%/*}" --help &>/dev/null; then
    echo "⚠️  Warning: Unable to verify registry login"
    echo "   You may need to login first:"
    echo "   helm registry login ${REGISTRY_URL%%/*} -u <username>"
    echo ""
fi

# Push to OCI registry
echo "📤 Pushing chart..."
helm push "${CHART_PACKAGE}" "oci://${REGISTRY_URL}" --insecure-skip-tls-verify

echo ""
echo "✅ Chart pushed successfully!"
echo ""
echo "To install from OCI registry, run:"
echo "  helm install tinyolly oci://${REGISTRY_URL}/tinyolly \\"
echo "    --version $(basename "${CHART_PACKAGE}" .tgz | sed 's/tinyolly-//') \\"
echo "    --namespace tinyolly \\"
echo "    --create-namespace"
