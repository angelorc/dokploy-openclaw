#!/usr/bin/env bash
set -e

STATE_DIR="${OPENCLAW_STATE_DIR:-/data/.openclaw}"
WORKSPACE_DIR="${OPENCLAW_WORKSPACE_DIR:-/data/workspace}"

echo "[entrypoint] state dir: $STATE_DIR"
echo "[entrypoint] workspace dir: $WORKSPACE_DIR"

# ── 1. Auto-generate gateway token if not set ────────────────────────────────
if [ -z "${OPENCLAW_GATEWAY_TOKEN:-}" ]; then
    TOKEN_FILE="$STATE_DIR/gateway.token"
    if [ -f "$TOKEN_FILE" ]; then
        export OPENCLAW_GATEWAY_TOKEN="$(cat "$TOKEN_FILE")"
        echo "[entrypoint] gateway token loaded from $TOKEN_FILE"
    else
        mkdir -p "$STATE_DIR"
        export OPENCLAW_GATEWAY_TOKEN="$(node -e "console.log(require('crypto').randomBytes(32).toString('hex'))")"
        echo "$OPENCLAW_GATEWAY_TOKEN" > "$TOKEN_FILE"
        chmod 600 "$TOKEN_FILE"
        echo "[entrypoint] gateway token auto-generated (persisted to $TOKEN_FILE)"
    fi
fi

# ── 2. Validate at least one AI provider ─────────────────────────────────────
HAS_PROVIDER=0
for key in ANTHROPIC_API_KEY OPENAI_API_KEY OPENROUTER_API_KEY GEMINI_API_KEY \
           XAI_API_KEY GROQ_API_KEY MISTRAL_API_KEY CEREBRAS_API_KEY \
           VENICE_API_KEY MOONSHOT_API_KEY KIMI_API_KEY MINIMAX_API_KEY \
           ZAI_API_KEY AI_GATEWAY_API_KEY OPENCODE_API_KEY OPENCODE_ZEN_API_KEY \
           SYNTHETIC_API_KEY COPILOT_GITHUB_TOKEN XIAOMI_API_KEY; do
    [ -n "${!key:-}" ] && HAS_PROVIDER=1 && break
done
[ -n "${AWS_ACCESS_KEY_ID:-}" ] && [ -n "${AWS_SECRET_ACCESS_KEY:-}" ] && HAS_PROVIDER=1
[ -n "${OLLAMA_BASE_URL:-}" ] && HAS_PROVIDER=1
if [ "$HAS_PROVIDER" -eq 0 ]; then
    echo "[entrypoint] WARNING: No AI provider API key detected."
    echo "[entrypoint] Set one of: ANTHROPIC_API_KEY, OPENAI_API_KEY, OPENROUTER_API_KEY, etc."
    echo "[entrypoint] The gateway will start with --allow-unconfigured. Configure via Control UI or mount openclaw.json."
fi

# ── 3. Install extra apt packages (optional) ─────────────────────────────────
if [ -n "${OPENCLAW_DOCKER_APT_PACKAGES:-}" ]; then
    echo "[entrypoint] installing extra packages: $OPENCLAW_DOCKER_APT_PACKAGES"
    apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        $OPENCLAW_DOCKER_APT_PACKAGES && rm -rf /var/lib/apt/lists/*
fi

# ── 4. Create directories ────────────────────────────────────────────────────
mkdir -p "$STATE_DIR" "$WORKSPACE_DIR"
export OPENCLAW_STATE_DIR="$STATE_DIR"
export OPENCLAW_WORKSPACE_DIR="$WORKSPACE_DIR"
export HOME="${STATE_DIR%/.openclaw}"

# ── 5. Generate Caddy snippets ───────────────────────────────────────────────
CADDY_DIR="/app/caddy.d"
mkdir -p "$CADDY_DIR"

# Auth snippet
if [ -n "${AUTH_PASSWORD:-}" ]; then
    AUTH_USER="${AUTH_USERNAME:-admin}"
    BCRYPT_HASH="$(caddy hash-password --plaintext "$AUTH_PASSWORD")"
    cat > "$CADDY_DIR/auth.caddyfile" <<EOF
(auth_block) {
    basic_auth {
        $AUTH_USER $BCRYPT_HASH
    }
}
EOF
    echo "[entrypoint] Caddy auth snippet generated (basicauth enabled)"
else
    cat > "$CADDY_DIR/auth.caddyfile" <<'EOF'
(auth_block) {
}
EOF
    echo "[entrypoint] Caddy auth snippet: no AUTH_PASSWORD set (no auth)"
fi

# Hooks snippet
HOOKS_ENABLED="${HOOKS_ENABLED:-}"
HOOKS_PATH="${HOOKS_PATH:-/hooks}"
if [ "${HOOKS_ENABLED,,}" = "true" ] || [ "$HOOKS_ENABLED" = "1" ]; then
    GW_PORT="${OPENCLAW_GATEWAY_PORT:-18789}"
    GW_TOKEN="${OPENCLAW_GATEWAY_TOKEN:-}"
    cat > "$CADDY_DIR/hooks.caddyfile" <<EOF
handle ${HOOKS_PATH}* {
    reverse_proxy localhost:${GW_PORT} {
        header_up Authorization "Bearer ${GW_TOKEN}"
    }
}
EOF
    echo "[entrypoint] Caddy hooks snippet generated (path: $HOOKS_PATH)"
else
    : > "$CADDY_DIR/hooks.caddyfile"
fi

# ── 6. Auto-fix doctor suggestions ──────────────────────────────────────────
echo "[entrypoint] running openclaw doctor --fix..."
cd /opt/openclaw/app
openclaw doctor --fix 2>&1 || true

# ── 7. Start Caddy (background) ─────────────────────────────────────────────
echo "[entrypoint] starting Caddy on port ${PORT:-8080}..."
caddy start --config /app/Caddyfile --adapter caddyfile

# ── 8. Clean stale lock files ────────────────────────────────────────────────
rm -f /tmp/openclaw-gateway.lock "$STATE_DIR/gateway.lock" 2>/dev/null || true

# ── 9. Start OpenClaw gateway (PID 1) ───────────────────────────────────────
echo "[entrypoint] starting openclaw gateway on port ${OPENCLAW_GATEWAY_PORT:-18789}..."
exec openclaw gateway \
    --port "${OPENCLAW_GATEWAY_PORT:-18789}" \
    --verbose \
    --allow-unconfigured \
    --bind "${OPENCLAW_GATEWAY_BIND:-loopback}" \
    --token "$OPENCLAW_GATEWAY_TOKEN"
