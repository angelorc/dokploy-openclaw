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

# ── 3. Install extra apt packages (optional) ─────────────────────────────────
if [ -n "${OPENCLAW_DOCKER_APT_PACKAGES:-}" ]; then
    echo "[entrypoint] installing extra packages: $OPENCLAW_DOCKER_APT_PACKAGES"
    apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        $OPENCLAW_DOCKER_APT_PACKAGES && rm -rf /var/lib/apt/lists/*
fi

# ── 4. Create directories ────────────────────────────────────────────────────
mkdir -p "$STATE_DIR" "$STATE_DIR/credentials" "$WORKSPACE_DIR"
chmod 700 "$STATE_DIR"
export OPENCLAW_STATE_DIR="$STATE_DIR"
export OPENCLAW_WORKSPACE_DIR="$WORKSPACE_DIR"
export HOME="${STATE_DIR%/.openclaw}"

# ── 4b. Seed default openclaw.json if missing ───────────────────────────────
CONFIG_FILE="$STATE_DIR/openclaw.json"
if [ ! -f "$CONFIG_FILE" ] && [ -f /app/openclaw.json.example ]; then
    cp /app/openclaw.json.example "$CONFIG_FILE"
    echo "[entrypoint] seeded default config from openclaw.json.example"
fi

# ── 5. Auto-fix doctor suggestions ──────────────────────────────────────────
echo "[entrypoint] running openclaw doctor --fix..."
cd /opt/openclaw/app
openclaw doctor --fix 2>&1 || true

# ── 5b. Ensure critical gateway settings for reverse-proxy operation ────────
# doctor --fix may overwrite openclaw.json and strip the gateway section.
# openclaw config set is unreliable when the gateway isn't running yet,
# so we merge the required settings directly into the JSON file using Node.
# - gateway.mode "local" is required for the gateway to start properly.
# - allowInsecureAuth is required when the Control UI connects through a
#   reverse proxy (Dokploy/Traefik) — without it the gateway rejects
#   connections that lack device identity.
if [ -f "$CONFIG_FILE" ]; then
    node -e "
      const fs = require('fs');
      const cfg = JSON.parse(fs.readFileSync('$CONFIG_FILE', 'utf8'));
      cfg.gateway = cfg.gateway || {};
      cfg.gateway.mode = 'local';
      cfg.gateway.controlUi = cfg.gateway.controlUi || {};
      cfg.gateway.controlUi.enabled = true;
      cfg.gateway.controlUi.allowInsecureAuth = true;
      fs.writeFileSync('$CONFIG_FILE', JSON.stringify(cfg, null, 2) + '\n');
    "
    echo "[entrypoint] ensured gateway.mode=local and controlUi.allowInsecureAuth=true in config"
fi

# ── 6. Clean stale lock files ────────────────────────────────────────────────
rm -f /tmp/openclaw-gateway.lock "$STATE_DIR/gateway.lock" 2>/dev/null || true

# ── 7. Start OpenClaw gateway (PID 1) ───────────────────────────────────────
GW_PORT="${OPENCLAW_GATEWAY_PORT:-${PORT:-18789}}"
echo "[entrypoint] starting openclaw gateway on port ${GW_PORT}..."
exec openclaw gateway \
    --port "${GW_PORT}" \
    --verbose \
    --allow-unconfigured \
    --bind "${OPENCLAW_GATEWAY_BIND:-lan}" \
    --token "$OPENCLAW_GATEWAY_TOKEN"
