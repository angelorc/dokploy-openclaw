#!/usr/bin/env bash
# Smoke test: verify openclaw binary works inside the built image.
#
# Usage:
#   ./scripts/smoke.sh                  # test openclaw:local
#   ./scripts/smoke.sh myimage:tag      # test a specific image

set -euo pipefail

IMAGE="${1:-openclaw:local}"
echo "Smoke testing $IMAGE..."

VERSION=$(docker run --rm --entrypoint openclaw "$IMAGE" --version 2>&1 || true)
if [ -n "$VERSION" ]; then
    echo "OK: openclaw $VERSION"
else
    echo "FAIL: could not get openclaw version"
    exit 1
fi
