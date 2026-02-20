# dokploy-openclaw

Docker image for deploying [OpenClaw](https://github.com/nicepkg/openclaw) on [Dokploy](https://dokploy.com). The gateway is exposed directly — no intermediate proxy — so Traefik (or any reverse proxy) connects straight to it.

## Architecture

```
┌─────────────────────────────────────────────────┐
│  Docker container (dokploy-openclaw)            │
│                                                 │
│  entrypoint.sh                                  │
│    1. auto-generate gateway token (if not set)  │
│    2. validate env vars (warning if no provider)│
│    3. seed default config (if missing)          │
│    4. exec openclaw gateway                     │
│                                                 │
│  ┌────────────────────────────────────────┐     │
│  │  openclaw gateway  :18789              │     │
│  │  (bearer token auth)                   │     │
│  └────────────────────────────────────────┘     │
│                                                 │
└─────────────────────────────────────────────────┘
        ▲
        │  Traefik / Dokploy (TLS + optional basic auth)
        │
    internet
```

## Quick Start

```bash
# 1. Copy environment template
cp .env.example .env

# 2. Edit .env -- set at least one AI provider key
#    ANTHROPIC_API_KEY=sk-ant-...

# 3. Start services
docker compose up -d
```

The Control UI will be available at `http://localhost:18789`. Authenticate with the gateway token printed in the container logs (`docker compose logs openclaw | grep "gateway token"`).

## Configuration

There are three ways to configure OpenClaw:

### 1. Environment variables (simplest)

Set AI provider API keys as env vars in `.env` or Dokploy's environment tab. OpenClaw auto-detects them:

```bash
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
```

See [.env.example](.env.example) for all supported env vars.

### 2. Mount `openclaw.json` (full control)

For channels, models, tools, hooks, and all other OpenClaw settings, mount a JSON5 config file:

```bash
docker run -v ./openclaw.json:/data/.openclaw/openclaw.json ...
```

Or in `docker-compose.yml`:

```yaml
volumes:
  - ./openclaw.json:/data/.openclaw/openclaw.json
```

See [openclaw.json.example](openclaw.json.example) for a reference template. The config supports `${VAR}` substitution for secrets.

For **Dokploy AutoDeploy**, do not mount config files from `./` repository paths. Use **Advanced -> Mounts** and reference Dokploy files:

```yaml
volumes:
  - ../files/openclaw.json:/data/.openclaw/openclaw.json:ro
```

This avoids broken file references after git-based redeploys.

### 3. Control UI (browser-based)

After first boot, open `http://localhost:18789` and use the built-in Control UI to configure OpenClaw interactively. Changes are hot-reloaded.

## Deploying with Traefik / Dokploy

Since the gateway is exposed directly, configure auth and routing in Traefik:

### Mounts and volumes (recommended)

The compose file is optimized for Dokploy with:

- Named volumes for persistent OpenClaw state and workspace (`openclaw-state`, `openclaw-workspace`)
- Optional Dokploy file mounts via `../files/*` for user-managed configs

Why this split:

- Named volumes are better for Dokploy Volume Backups.
- `../files/*` mounts are better for user-editable config files managed in Dokploy UI.

### Basic auth middleware

Add Traefik labels to the `openclaw` service in your compose file:

```yaml
labels:
  - "traefik.http.middlewares.openclaw-auth.basicauth.users=admin:$$apr1$$..."
  - "traefik.http.routers.openclaw.middlewares=openclaw-auth"
```

Generate the password hash with: `htpasswd -nB admin`

### Browser sidecar routing

To expose the VNC web UI through Traefik, add a separate route:

```yaml
labels:
  - "traefik.http.routers.openclaw-browser.rule=Host(`your-domain.com`) && PathPrefix(`/browser/`)"
  - "traefik.http.routers.openclaw-browser.service=openclaw-browser"
  - "traefik.http.services.openclaw-browser.loadbalancer.server.port=3000"
  - "traefik.http.routers.openclaw-browser.middlewares=openclaw-auth"
```

### Token injection (optional)

If you want Traefik to inject the gateway token so users don't need it:

```yaml
labels:
  - "traefik.http.middlewares.openclaw-token.headers.customrequestheaders.Authorization=Bearer YOUR_TOKEN"
  - "traefik.http.routers.openclaw.middlewares=openclaw-auth,openclaw-token"
```

## Hooks

Webhook automation is configured in `openclaw.json`, not via environment variables:

```json5
{
  hooks: {
    enabled: true,
    token: "${HOOKS_TOKEN}",
    path: "/hooks",
  },
}
```

See [openclaw.json.example](openclaw.json.example) and the [hooks documentation](https://openclaw.ai/automation/hooks).

## Browser Sidecar

The `browser` service in `docker-compose.yml` runs a headless Chromium instance ([linuxserver/chromium](https://docs.linuxserver.io/images/docker-chromium)) with a Chrome DevTools Protocol (CDP) proxy.

**How it works:**

1. Chromium listens on port 9222 (CDP) and port 3000 (VNC web UI)
2. An nginx proxy on port 9223 rewrites the `Host` header to `localhost` so Chrome accepts remote CDP connections
3. The openclaw container connects to `browser:9223` for browser automation
4. The VNC web UI (port 3000) needs a separate Traefik route if you want external access (see above)

No ports are exposed from the browser container directly — access goes through Traefik.

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
   docker run -d -p 18789:18789 \
     -e ANTHROPIC_API_KEY=sk-ant-... \
     -v openclaw-state:/data/.openclaw \
     -v openclaw-workspace:/data/workspace \
     openclaw:local
   ```

3. **Get gateway token from logs:**
   ```bash
   docker logs <container-id> 2>&1 | grep "gateway token"
   ```

4. **Health check:**
   ```bash
   curl http://localhost:18789/healthz
   # Expected: 401 (no token)

   curl -H "Authorization: Bearer YOUR_TOKEN" http://localhost:18789/healthz
   # Expected: 200 OK
   ```

5. **UI access:** Open `http://localhost:18789` in a browser and enter the gateway token.

6. **Full compose:**
   ```bash
   docker compose up -d
   # Both openclaw and browser containers should be running
   docker compose ps
   ```
