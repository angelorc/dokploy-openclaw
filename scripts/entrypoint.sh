#!/usr/bin/env bash
set -e

STATE_DIR="${OPENCLAW_STATE_DIR:-/data/.openclaw}"
WORKSPACE_DIR="${OPENCLAW_WORKSPACE_DIR:-/data/workspace}"
CONFIG_FILE="${OPENCLAW_CONFIG_PATH:-$STATE_DIR/openclaw.json}"

echo "[entrypoint] state dir: $STATE_DIR"
echo "[entrypoint] workspace dir: $WORKSPACE_DIR"
echo "[entrypoint] config file: $CONFIG_FILE"

# ── 1. Resolve gateway token ──────────────────────────────────────────────────
TOKEN_FILE="$STATE_DIR/gateway.token"
if [ -n "${OPENCLAW_GATEWAY_TOKEN:-}" ]; then
    # Token explicitly set via environment — persist to file so healthchecks work
    mkdir -p "$STATE_DIR"
    echo "$OPENCLAW_GATEWAY_TOKEN" > "$TOKEN_FILE"
    chmod 600 "$TOKEN_FILE"
    echo "[entrypoint] gateway token set from environment (persisted to $TOKEN_FILE)"
elif [ -f "$TOKEN_FILE" ]; then
    export OPENCLAW_GATEWAY_TOKEN="$(cat "$TOKEN_FILE")"
    echo "[entrypoint] gateway token loaded from $TOKEN_FILE"
else
    # No token set and no file — auto-generate
    mkdir -p "$STATE_DIR"
    export OPENCLAW_GATEWAY_TOKEN="$(node -e "console.log(require('crypto').randomBytes(32).toString('hex'))")"
    echo "$OPENCLAW_GATEWAY_TOKEN" > "$TOKEN_FILE"
    chmod 600 "$TOKEN_FILE"
    echo "[entrypoint] gateway token auto-generated (persisted to $TOKEN_FILE)"
fi
echo "[entrypoint] gateway token: $OPENCLAW_GATEWAY_TOKEN"

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

# ── 3. Create directories ────────────────────────────────────────────────────
mkdir -p "$STATE_DIR" "$STATE_DIR/credentials" "$WORKSPACE_DIR"
chmod 700 "$STATE_DIR"
export OPENCLAW_STATE_DIR="$STATE_DIR"
export OPENCLAW_WORKSPACE_DIR="$WORKSPACE_DIR"
export OPENCLAW_CONFIG_PATH="$CONFIG_FILE"

# ── 3b. Seed default openclaw.json only when missing ─────────────────────────
if [ ! -f "$CONFIG_FILE" ] && [ -f /app/openclaw.json.example ]; then
    mkdir -p "$(dirname "$CONFIG_FILE")"
    cp /app/openclaw.json.example "$CONFIG_FILE"
    echo "[entrypoint] seeded default config from openclaw.json.example (missing config)"
fi

# ── 4. Clean stale lock files ────────────────────────────────────────────────
rm -f /tmp/openclaw-gateway.lock "$STATE_DIR/gateway.lock" 2>/dev/null || true

# ── 5. Start OpenClaw gateway (PID 1) ───────────────────────────────────────
GW_PORT="${OPENCLAW_GATEWAY_PORT:-${PORT:-18789}}"
echo "[entrypoint] starting openclaw gateway on port ${GW_PORT}..."
exec openclaw gateway \
    --port "${GW_PORT}" \
    --verbose \
    --allow-unconfigured \
    --bind "${OPENCLAW_GATEWAY_BIND:-lan}" \
    --token "$OPENCLAW_GATEWAY_TOKEN"
