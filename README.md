# dokploy-openclaw

Docker image for deploying [OpenClaw](https://github.com/nicepkg/openclaw) on [Dokploy](https://dokploy.com). Features a schema-driven Python config engine, Caddy reverse proxy, and a single multi-stage Dockerfile.

## Architecture

```
┌─────────────────────────────────────────────────────┐
│  Docker container (dokploy-openclaw)                │
│                                                     │
│  entrypoint.sh                                      │
│    1. validate env vars                             │
│    2. auto-generate gateway token (if not set)      │
│    3. configure.py (env -> openclaw.json + caddy.d/)│
│    4. openclaw doctor --fix                         │
│    5. caddy start (background)                      │
│    6. exec openclaw gateway                         │
│                                                     │
│  ┌──────────┐  :8080   ┌────────────────┐          │
│  │  Caddy    │ -------> │  openclaw      │          │
│  │  (basic   │  proxy   │  gateway       │          │
│  │   auth)   │  :18789  │  :18789        │          │
│  └──────────┘          └────────────────┘          │
│                                                     │
│  /browser/ -> browser sidecar:3000 (VNC web UI)    │
└─────────────────────────────────────────────────────┘
```

## Quick Start

```bash
# 1. Copy environment template
cp .env.example .env

# 2. Edit .env -- set at least one AI provider key and AUTH_PASSWORD
#    ANTHROPIC_API_KEY=sk-ant-...
#    AUTH_PASSWORD=changeme

# 3. Start services
docker compose up -d
```

The UI will be available at `http://localhost:8080`. Login with the username `admin` (default) and the password you set in `AUTH_PASSWORD`.

## Environment Variables

All environment variables are documented in [.env.example](.env.example). Key sections:

| Section | Key Variables | Notes |
|---------|--------------|-------|
| **AI Providers** | `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `OPENROUTER_API_KEY`, ... | At least one required |
| **Auth** | `AUTH_USERNAME`, `AUTH_PASSWORD` | Caddy basic auth on all routes except `/healthz` |
| **Gateway** | `OPENCLAW_GATEWAY_TOKEN`, `OPENCLAW_GATEWAY_PORT` | Token auto-generated if not set |
| **Model** | `OPENCLAW_PRIMARY_MODEL` | Auto-selected from first configured provider |
| **Channels** | `TELEGRAM_BOT_TOKEN`, `DISCORD_BOT_TOKEN`, `SLACK_BOT_TOKEN`, `WHATSAPP_ENABLED` | Optional messaging integrations |
| **Browser** | `BROWSER_CDP_URL`, `BROWSER_EVALUATE_ENABLED` | CDP sidecar connection |
| **Hooks** | `HOOKS_ENABLED`, `HOOKS_TOKEN` | Webhook automation endpoints |
| **Providers** | `AI_GATEWAY_BASE_URL`, `ANTHROPIC_BASE_URL`, ... | Custom base URL overrides |

## OPENCLAW_JSON__* Convention

Any environment variable matching `OPENCLAW_JSON__path__to__key=value` is applied directly to `openclaw.json` at the JSON path `path.to.key`. Double underscores (`__`) become dot-separated nesting levels.

This lets you configure **any** OpenClaw setting via environment variables, even settings not explicitly listed in `.env.example`. Types are auto-detected (numbers, booleans, JSON objects/arrays).

**Examples:**

```bash
# Set max concurrent agents
OPENCLAW_JSON__agents__defaults__maxConcurrent=5
# Result: {"agents": {"defaults": {"maxConcurrent": 5}}}

# Set compaction mode
OPENCLAW_JSON__agents__defaults__compaction__mode=safeguard
# Result: {"agents": {"defaults": {"compaction": {"mode": "safeguard"}}}}

# Set primary model via JSON path
OPENCLAW_JSON__models__primaryModel=opencode/kimi-k2.5
# Result: {"models": {"primaryModel": "opencode/kimi-k2.5"}}
```

## Browser Sidecar

The `browser` service in `docker-compose.yml` runs a headless Chromium instance ([linuxserver/chromium](https://docs.linuxserver.io/images/docker-chromium)) with a Chrome DevTools Protocol (CDP) proxy.

**How it works:**

1. Chromium listens on port 9222 (CDP) and port 3000 (VNC web UI)
2. An nginx proxy on port 9223 rewrites the `Host` header to `localhost` so Chrome accepts remote CDP connections
3. The openclaw container connects to `browser:9223` for browser automation
4. The VNC web UI is accessible at `/browser/` through Caddy (auth-protected)

No ports are exposed from the browser container directly -- all access goes through Caddy on port 8080.

## Building from Source

Use the build helper script:

```bash
# Build both openclaw and browser images
./scripts/build.sh

# Build only the openclaw image
./scripts/build.sh openclaw

# Build only the browser sidecar
./scripts/build.sh browser

# Pin to a specific OpenClaw version
OPENCLAW_GIT_REF=v2026.1.29 ./scripts/build.sh

# Custom image tags
IMAGE_TAG=myregistry/openclaw:v1 BROWSER_TAG=myregistry/openclaw-browser:v1 ./scripts/build.sh
```

Run a smoke test after building:

```bash
./scripts/smoke.sh              # tests openclaw:local
./scripts/smoke.sh myimage:tag  # tests a specific image
```

## Verification

After deployment, verify everything is working:

1. **Build locally:**
   ```bash
   ./scripts/build.sh
   ```

2. **Minimal run (auto-generates gateway token):**
   ```bash
   docker run -d -p 8080:8080 \
     -e ANTHROPIC_API_KEY=sk-ant-... \
     -e AUTH_PASSWORD=changeme \
     -v openclaw-data:/data \
     openclaw:local
   ```

3. **Health check:**
   ```bash
   curl http://localhost:8080/healthz
   # Expected: 200 OK
   ```

4. **Auth required:**
   ```bash
   curl http://localhost:8080/
   # Expected: 401 Unauthorized
   ```

5. **UI access:** Open `http://localhost:8080` in a browser and login with `admin` / your password.

6. **Convention passthrough test:**
   ```bash
   docker run -d -p 8080:8080 \
     -e ANTHROPIC_API_KEY=sk-ant-... \
     -e AUTH_PASSWORD=changeme \
     -e OPENCLAW_JSON__agents__defaults__maxConcurrent=10 \
     -v openclaw-data:/data \
     openclaw:local

   # Verify:
   docker exec <container> cat /data/.openclaw/openclaw.json | python3 -m json.tool
   # agents.defaults.maxConcurrent should be 10
   ```

7. **Full compose:**
   ```bash
   docker compose up -d
   # Both openclaw and browser containers should be running
   docker compose ps
   ```

8. **Browser proxy:** Open `http://localhost:8080/browser/` for the VNC web UI.
