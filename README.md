# dokploy-openclaw

Docker image for deploying [OpenClaw](https://github.com/nicepkg/openclaw) on [Dokploy](https://dokploy.com). Features Caddy reverse proxy with basic auth and a single multi-stage Dockerfile.

## Architecture

```
┌─────────────────────────────────────────────────┐
│  Docker container (dokploy-openclaw)            │
│                                                 │
│  entrypoint.sh                                  │
│    1. auto-generate gateway token (if not set)  │
│    2. validate env vars (warning if no provider)│
│    3. generate Caddy auth + hooks snippets      │
│    4. openclaw doctor --fix                     │
│    5. caddy start (background)                  │
│    6. exec openclaw gateway                     │
│                                                 │
│  ┌──────────┐  :8080   ┌────────────────┐      │
│  │  Caddy    │ -------> │  openclaw      │      │
│  │  (basic   │  proxy   │  gateway       │      │
│  │   auth)   │  :18789  │  :18789        │      │
│  └──────────┘          └────────────────┘      │
│                                                 │
│  /browser/ -> browser sidecar:3000 (VNC web UI) │
└─────────────────────────────────────────────────┘
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

For channels, models, tools, and all other OpenClaw settings, mount a JSON5 config file:

```bash
docker run -v ./openclaw.json:/data/.openclaw/openclaw.json ...
```

Or in `docker-compose.yml`:

```yaml
volumes:
  - ./openclaw.json:/data/.openclaw/openclaw.json
```

See [openclaw.json.example](openclaw.json.example) for a reference template. The config supports `${VAR}` substitution for secrets.

### 3. Control UI (browser-based)

After first boot, open `http://localhost:8080` and use the built-in Control UI to configure OpenClaw interactively. Changes are hot-reloaded.

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

6. **Config mount test:**
   ```bash
   docker run -d -p 8080:8080 \
     -e ANTHROPIC_API_KEY=sk-ant-... \
     -e AUTH_PASSWORD=changeme \
     -v ./openclaw.json:/data/.openclaw/openclaw.json \
     -v openclaw-data:/data \
     openclaw:local
   ```

7. **Full compose:**
   ```bash
   docker compose up -d
   # Both openclaw and browser containers should be running
   docker compose ps
   ```

8. **Browser proxy:** Open `http://localhost:8080/browser/` for the VNC web UI.
