#!/usr/bin/env bash
# Build dokploy-openclaw Docker images locally.
#
# Usage:
#   ./scripts/build.sh                  # build both openclaw + browser
#   ./scripts/build.sh openclaw         # build openclaw only
#   ./scripts/build.sh browser          # build browser sidecar only
#   OPENCLAW_GIT_REF=v2026.1.29 ./scripts/build.sh  # pin to a specific version

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

IMAGE_TAG="${IMAGE_TAG:-openclaw:local}"
BROWSER_TAG="${BROWSER_TAG:-openclaw-browser:local}"
GIT_REF="${OPENCLAW_GIT_REF:-main}"

case "${1:-all}" in
    openclaw)
        echo "==> Building openclaw image ($IMAGE_TAG, ref=$GIT_REF)..."
        docker build --build-arg OPENCLAW_GIT_REF="$GIT_REF" -t "$IMAGE_TAG" .
        echo "==> Built: $IMAGE_TAG"
        ;;
    browser)
        echo "==> Building browser sidecar ($BROWSER_TAG)..."
        docker build -f Dockerfile.browser -t "$BROWSER_TAG" .
        echo "==> Built: $BROWSER_TAG"
        ;;
    all)
        "$0" openclaw
        "$0" browser
        echo ""
        echo "Done. Images: $IMAGE_TAG, $BROWSER_TAG"
        ;;
    *)
        echo "Usage: $0 [all|openclaw|browser]"
        exit 1
        ;;
esac
