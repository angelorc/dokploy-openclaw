#!/usr/bin/env python3
"""Generate openclaw.json + Caddy snippets from environment variables.

Schema-driven: add new mappings to SCHEMA, the engine applies them generically.
Convention passthrough: OPENCLAW_JSON__path__to__key=value -> {"path":{"to":{"key":"value"}}}
"""

import json
import os
import subprocess
import sys
from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────────────────────

STATE_DIR = os.environ.get("OPENCLAW_STATE_DIR", "/data/.openclaw").rstrip("/")
WORKSPACE_DIR = os.environ.get("OPENCLAW_WORKSPACE_DIR", "/data/workspace").rstrip("/")
CONFIG_FILE = os.environ.get("OPENCLAW_CONFIG_PATH", os.path.join(STATE_DIR, "openclaw.json"))
CUSTOM_CONFIG = os.environ.get("OPENCLAW_CUSTOM_CONFIG", "/app/config/openclaw.json")

# ── Schema: Built-in Providers ─────────────────────────────────────────────────
# These are auto-detected by OpenClaw when the env var is set.
# We do NOT write models.providers entries for these.

BUILTIN_PROVIDERS = [
    ("ANTHROPIC_API_KEY",    "Anthropic",         "anthropic"),
    ("OPENAI_API_KEY",       "OpenAI",            "openai"),
    ("OPENROUTER_API_KEY",   "OpenRouter",         "openrouter"),
    ("GEMINI_API_KEY",       "Google Gemini",     "google"),
    ("XAI_API_KEY",          "xAI",               "xai"),
    ("GROQ_API_KEY",         "Groq",              "groq"),
    ("MISTRAL_API_KEY",      "Mistral",           "mistral"),
    ("CEREBRAS_API_KEY",     "Cerebras",          "cerebras"),
    ("ZAI_API_KEY",          "ZAI",               "zai"),
    ("AI_GATEWAY_API_KEY",   "Vercel AI Gateway", "vercel-ai-gateway"),
    ("COPILOT_GITHUB_TOKEN", "GitHub Copilot",    "github-copilot"),
]

# ── Schema: Custom Providers ───────────────────────────────────────────────────
# These need explicit models.providers entries (not in OpenClaw's built-in catalog).

CUSTOM_PROVIDERS = [
    {"key": "venice",      "env": "VENICE_API_KEY",    "api": "openai-completions",
     "baseUrl": "https://api.venice.ai/api/v1",
     "models": [{"id": "llama-3.3-70b", "name": "Llama 3.3 70B", "contextWindow": 128000}]},
    {"key": "minimax",     "env": "MINIMAX_API_KEY",   "api": "anthropic-messages",
     "baseUrl": "https://api.minimax.io/anthropic",
     "models": [{"id": "MiniMax-M2.1", "name": "MiniMax M2.1", "contextWindow": 200000}]},
    {"key": "moonshot",    "env": "MOONSHOT_API_KEY",  "api": "openai-completions",
     "baseUrlEnv": "MOONSHOT_BASE_URL", "baseUrlDefault": "https://api.moonshot.ai/v1",
     "models": [{"id": "kimi-k2.5", "name": "Kimi K2.5", "contextWindow": 128000}]},
    {"key": "kimi-coding", "env": "KIMI_API_KEY",      "api": "anthropic-messages",
     "baseUrlEnv": "KIMI_BASE_URL", "baseUrlDefault": "https://api.moonshot.ai/anthropic",
     "models": [{"id": "k2p5", "name": "Kimi K2P5", "contextWindow": 128000}]},
    {"key": "synthetic",   "env": "SYNTHETIC_API_KEY",  "api": "anthropic-messages",
     "baseUrl": "https://api.synthetic.new/anthropic",
     "models": [{"id": "hf:MiniMaxAI/MiniMax-M2.1", "name": "MiniMax M2.1", "contextWindow": 192000}]},
    {"key": "xiaomi",      "env": "XIAOMI_API_KEY",    "api": "anthropic-messages",
     "baseUrl": "https://api.xiaomimimo.com/anthropic",
     "models": [{"id": "mimo-v2-flash", "name": "MiMo v2 Flash", "contextWindow": 262144}]},
]
# Bedrock and Ollama are handled separately (special config structure).

# ── Schema: Primary Model Priority ────────────────────────────────────────────
# First match with a set env var wins. Special keys _OPENCODE_KEY and _OLLAMA_URL
# are resolved before iteration.

PRIMARY_MODEL_PRIORITY = [
    ("ANTHROPIC_API_KEY",      "anthropic/claude-opus-4-5-20251101"),
    ("OPENAI_API_KEY",         "openai/gpt-5.2"),
    ("OPENROUTER_API_KEY",     "openrouter/anthropic/claude-opus-4-5"),
    ("GEMINI_API_KEY",         "google/gemini-2.5-pro"),
    ("_OPENCODE_KEY",          "opencode/claude-opus-4-5"),
    ("COPILOT_GITHUB_TOKEN",   "github-copilot/claude-opus-4-5"),
    ("XAI_API_KEY",            "xai/grok-3"),
    ("GROQ_API_KEY",           "groq/llama-3.3-70b-versatile"),
    ("MISTRAL_API_KEY",        "mistral/mistral-large-latest"),
    ("CEREBRAS_API_KEY",       "cerebras/llama-3.3-70b"),
    ("VENICE_API_KEY",         "venice/llama-3.3-70b"),
    ("MOONSHOT_API_KEY",       "moonshot/kimi-k2.5"),
    ("KIMI_API_KEY",           "kimi-coding/k2p5"),
    ("MINIMAX_API_KEY",        "minimax/MiniMax-M2.1"),
    ("SYNTHETIC_API_KEY",      "synthetic/hf:MiniMaxAI/MiniMax-M2.1"),
    ("ZAI_API_KEY",            "zai/glm-4.7"),
    ("AI_GATEWAY_API_KEY",     "vercel-ai-gateway/anthropic/claude-opus-4.5"),
    ("XIAOMI_API_KEY",         "xiaomi/mimo-v2-flash"),
    ("AWS_ACCESS_KEY_ID",      "amazon-bedrock/anthropic.claude-opus-4-5-20251101-v1:0"),
    ("_OLLAMA_URL",            "ollama/llama3.3"),
]

# ── Schema: Channels ──────────────────────────────────────────────────────────

CHANNELS = [
    {
        "key": "telegram", "gate": "TELEGRAM_BOT_TOKEN", "merge": True,
        "tokenField": "botToken",
        "fields": [
            ("TELEGRAM_DM_POLICY",              "dmPolicy",                    "str"),
            ("TELEGRAM_GROUP_POLICY",           "groupPolicy",                 "str"),
            ("TELEGRAM_REPLY_TO_MODE",          "replyToMode",                 "str"),
            ("TELEGRAM_CHUNK_MODE",             "chunkMode",                   "str"),
            ("TELEGRAM_STREAM_MODE",            "streamMode",                  "str"),
            ("TELEGRAM_REACTION_NOTIFICATIONS", "reactionNotifications",       "str"),
            ("TELEGRAM_REACTION_LEVEL",         "reactionLevel",               "str"),
            ("TELEGRAM_PROXY",                  "proxy",                       "str"),
            ("TELEGRAM_WEBHOOK_URL",            "webhookUrl",                  "str"),
            ("TELEGRAM_WEBHOOK_SECRET",         "webhookSecret",               "str"),
            ("TELEGRAM_WEBHOOK_PATH",           "webhookPath",                 "str"),
            ("TELEGRAM_MESSAGE_PREFIX",         "messagePrefix",               "str"),
            ("TELEGRAM_LINK_PREVIEW",           "linkPreview",                 "bool_true"),
            ("TELEGRAM_ACTIONS_REACTIONS",      "actions.reactions",           "bool_true"),
            ("TELEGRAM_ACTIONS_STICKER",        "actions.sticker",             "bool_false"),
            ("TELEGRAM_TEXT_CHUNK_LIMIT",       "textChunkLimit",              "int"),
            ("TELEGRAM_MEDIA_MAX_MB",           "mediaMaxMb",                  "int"),
            ("TELEGRAM_ALLOW_FROM",             "allowFrom",                   "csv_smart"),
            ("TELEGRAM_GROUP_ALLOW_FROM",       "groupAllowFrom",              "csv_smart"),
            ("TELEGRAM_INLINE_BUTTONS",         "capabilities.inlineButtons",  "str"),
        ],
    },
    {
        "key": "discord", "gate": "DISCORD_BOT_TOKEN", "merge": True,
        "tokenField": "token",
        "fields": [
            ("DISCORD_DM_POLICY",              "dm.policy",                   "str"),
            ("DISCORD_GROUP_POLICY",           "groupPolicy",                 "str"),
            ("DISCORD_REPLY_TO_MODE",          "replyToMode",                 "str"),
            ("DISCORD_CHUNK_MODE",             "chunkMode",                   "str"),
            ("DISCORD_REACTION_NOTIFICATIONS", "reactionNotifications",       "str"),
            ("DISCORD_MESSAGE_PREFIX",         "messagePrefix",               "str"),
            ("DISCORD_ALLOW_BOTS",             "allowBots",                   "bool_false"),
            ("DISCORD_ACTIONS_REACTIONS",       "actions.reactions",           "bool_true"),
            ("DISCORD_ACTIONS_STICKERS",        "actions.stickers",           "bool_true"),
            ("DISCORD_ACTIONS_EMOJI_UPLOADS",   "actions.emojiUploads",       "bool_true"),
            ("DISCORD_ACTIONS_STICKER_UPLOADS", "actions.stickerUploads",     "bool_true"),
            ("DISCORD_ACTIONS_POLLS",           "actions.polls",              "bool_true"),
            ("DISCORD_ACTIONS_PERMISSIONS",     "actions.permissions",         "bool_true"),
            ("DISCORD_ACTIONS_MESSAGES",        "actions.messages",           "bool_true"),
            ("DISCORD_ACTIONS_THREADS",         "actions.threads",            "bool_true"),
            ("DISCORD_ACTIONS_PINS",            "actions.pins",               "bool_true"),
            ("DISCORD_ACTIONS_SEARCH",          "actions.search",             "bool_true"),
            ("DISCORD_ACTIONS_MEMBER_INFO",     "actions.memberInfo",         "bool_true"),
            ("DISCORD_ACTIONS_ROLE_INFO",       "actions.roleInfo",           "bool_true"),
            ("DISCORD_ACTIONS_CHANNEL_INFO",    "actions.channelInfo",        "bool_true"),
            ("DISCORD_ACTIONS_CHANNELS",        "actions.channels",           "bool_true"),
            ("DISCORD_ACTIONS_VOICE_STATUS",    "actions.voiceStatus",        "bool_true"),
            ("DISCORD_ACTIONS_EVENTS",          "actions.events",             "bool_true"),
            ("DISCORD_ACTIONS_ROLES",           "actions.roles",              "bool_false"),
            ("DISCORD_ACTIONS_MODERATION",      "actions.moderation",         "bool_false"),
            ("DISCORD_TEXT_CHUNK_LIMIT",        "textChunkLimit",             "int"),
            ("DISCORD_MAX_LINES_PER_MESSAGE",   "maxLinesPerMessage",         "int"),
            ("DISCORD_MEDIA_MAX_MB",            "mediaMaxMb",                 "int"),
            ("DISCORD_HISTORY_LIMIT",           "historyLimit",               "int"),
            ("DISCORD_DM_HISTORY_LIMIT",        "dmHistoryLimit",             "int"),
            ("DISCORD_DM_ALLOW_FROM",           "dm.allowFrom",               "csv"),
        ],
    },
    {
        "key": "slack",
        "gate": ["SLACK_BOT_TOKEN", "SLACK_APP_TOKEN"],
        "merge": True,
        "tokenField": ["botToken", "appToken"],
        "fields": [
            ("SLACK_USER_TOKEN",              "userToken",                    "str"),
            ("SLACK_SIGNING_SECRET",          "signingSecret",                "str"),
            ("SLACK_MODE",                    "mode",                         "str"),
            ("SLACK_WEBHOOK_PATH",            "webhookPath",                  "str"),
            ("SLACK_DM_POLICY",               "dm.policy",                    "str"),
            ("SLACK_GROUP_POLICY",            "groupPolicy",                  "str"),
            ("SLACK_REPLY_TO_MODE",           "replyToMode",                  "str"),
            ("SLACK_REACTION_NOTIFICATIONS",  "reactionNotifications",        "str"),
            ("SLACK_CHUNK_MODE",              "chunkMode",                    "str"),
            ("SLACK_MESSAGE_PREFIX",          "messagePrefix",                "str"),
            ("SLACK_ALLOW_BOTS",              "allowBots",                    "bool_false"),
            ("SLACK_ACTIONS_REACTIONS",        "actions.reactions",            "bool_true"),
            ("SLACK_ACTIONS_MESSAGES",         "actions.messages",            "bool_true"),
            ("SLACK_ACTIONS_PINS",             "actions.pins",                "bool_true"),
            ("SLACK_ACTIONS_MEMBER_INFO",      "actions.memberInfo",          "bool_true"),
            ("SLACK_ACTIONS_EMOJI_LIST",       "actions.emojiList",           "bool_true"),
            ("SLACK_HISTORY_LIMIT",           "historyLimit",                 "int"),
            ("SLACK_TEXT_CHUNK_LIMIT",        "textChunkLimit",               "int"),
            ("SLACK_MEDIA_MAX_MB",            "mediaMaxMb",                   "int"),
            ("SLACK_DM_ALLOW_FROM",           "dm.allowFrom",                 "csv"),
        ],
    },
    {
        "key": "whatsapp",
        "gate": "WHATSAPP_ENABLED",
        "gateCheck": "bool",
        "merge": False,
        "fields": [
            ("WHATSAPP_DM_POLICY",              "dmPolicy",                  "str"),
            ("WHATSAPP_GROUP_POLICY",           "groupPolicy",               "str"),
            ("WHATSAPP_MESSAGE_PREFIX",         "messagePrefix",             "str"),
            ("WHATSAPP_SELF_CHAT_MODE",         "selfChatMode",              "bool_false"),
            ("WHATSAPP_SEND_READ_RECEIPTS",     "sendReadReceipts",          "bool_true"),
            ("WHATSAPP_ACTIONS_REACTIONS",       "actions.reactions",         "bool_true"),
            ("WHATSAPP_MEDIA_MAX_MB",           "mediaMaxMb",                "int"),
            ("WHATSAPP_HISTORY_LIMIT",          "historyLimit",              "int"),
            ("WHATSAPP_DM_HISTORY_LIMIT",       "dmHistoryLimit",            "int"),
            ("WHATSAPP_ALLOW_FROM",             "allowFrom",                 "csv"),
            ("WHATSAPP_GROUP_ALLOW_FROM",       "groupAllowFrom",            "csv"),
            ("WHATSAPP_ACK_REACTION_EMOJI",     "ackReaction.emoji",         "str"),
            ("WHATSAPP_ACK_REACTION_DIRECT",    "ackReaction.direct",        "bool_true"),
            ("WHATSAPP_ACK_REACTION_GROUP",     "ackReaction.group",         "str"),
        ],
    },
]

# ── Schema: Browser Fields ────────────────────────────────────────────────────

BROWSER_FIELDS = [
    ("BROWSER_CDP_URL",                     "cdpUrl",                       "str"),
    ("BROWSER_EVALUATE_ENABLED",            "evaluateEnabled",              "bool_false"),
    ("BROWSER_SNAPSHOT_MODE",               "snapshotDefaults.mode",        "str"),
    ("BROWSER_REMOTE_TIMEOUT_MS",           "remoteCdpTimeoutMs",           "int"),
    ("BROWSER_REMOTE_HANDSHAKE_TIMEOUT_MS", "remoteCdpHandshakeTimeoutMs",  "int"),
    ("BROWSER_DEFAULT_PROFILE",             "defaultProfile",               "str"),
]

# ── Schema: Hooks Fields ──────────────────────────────────────────────────────

HOOKS_FIELDS = [
    ("HOOKS_TOKEN",  "token",  "str"),
    ("HOOKS_PATH",   "path",   "str"),
]


# ══════════════════════════════════════════════════════════════════════════════
# Generic Engine
# ══════════════════════════════════════════════════════════════════════════════

def deep_merge(target, source):
    """Merge source dict into target. Arrays are replaced, not concatenated."""
    for key, val in source.items():
        if isinstance(val, dict) and isinstance(target.get(key), dict):
            deep_merge(target[key], val)
        else:
            target[key] = val
    return target


def set_nested(obj, dotpath, value):
    """Set a value at a dot-separated path: 'actions.reactions' -> obj['actions']['reactions']"""
    keys = dotpath.split(".")
    for k in keys[:-1]:
        obj = obj.setdefault(k, {})
    obj[keys[-1]] = value


def get_nested(obj, dotpath, default=None):
    """Get a value at a dot-separated path."""
    for k in dotpath.split("."):
        if not isinstance(obj, dict):
            return default
        obj = obj.get(k, default)
        if obj is default:
            return default
    return obj


def parse_value(raw, type_hint):
    """Parse env var string to typed value.

    Type hints:
      str        - passthrough
      int        - integer
      bool_true  - default true, only "false" turns it off
      bool_false - default false, only "true" turns it on
      csv        - comma-separated list of strings
      csv_smart  - comma-separated, integers for numeric values (Telegram user IDs)
    """
    if type_hint == "str":
        return raw
    if type_hint == "int":
        return int(raw)
    if type_hint == "bool_true":
        return raw.lower() != "false"
    if type_hint == "bool_false":
        return raw.lower() == "true"
    if type_hint == "csv":
        return [s.strip() for s in raw.split(",") if s.strip()]
    if type_hint == "csv_smart":
        result = []
        for s in raw.split(","):
            s = s.strip()
            if not s:
                continue
            try:
                result.append(int(s))
            except ValueError:
                result.append(s)
        return result
    return raw


def apply_fields(obj, fields):
    """Apply a list of (env_var, json_path, type) field mappings to obj."""
    for env_var, json_path, type_hint in fields:
        val = os.environ.get(env_var)
        if val is not None:
            set_nested(obj, json_path, parse_value(val, type_hint))


def _auto_type(raw):
    """Auto-detect type from string value."""
    if raw.lower() in ("true", "false"):
        return raw.lower() == "true"
    try:
        return int(raw)
    except ValueError:
        pass
    try:
        return float(raw)
    except ValueError:
        pass
    if raw.startswith(("[", "{")):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass
    return raw


def apply_convention_overrides(config):
    """Apply OPENCLAW_JSON__path__to__key=value overrides.

    Double underscore separates path components.
    Auto-detects types: integers, booleans, JSON arrays/objects, else string.
    """
    prefix = "OPENCLAW_JSON__"
    for key, raw in sorted(os.environ.items()):
        if not key.startswith(prefix):
            continue
        path = key[len(prefix):].replace("__", ".")
        value = _auto_type(raw)
        set_nested(config, path, value)
        print(f"[configure] convention override: {path} = {value!r}")


def ensure(obj, *keys):
    """Ensure nested path exists, return the innermost dict."""
    cur = obj
    for k in keys:
        if k not in cur or not isinstance(cur[k], dict):
            cur[k] = {}
        cur = cur[k]
    return cur


def remove_provider(config, has_custom_config, name, label, env_hint):
    """Remove a stale provider entry (only when no custom JSON is loaded)."""
    if not has_custom_config:
        providers = get_nested(config, "models.providers")
        if isinstance(providers, dict) and name in providers:
            print(f"[configure] removing {label} provider ({env_hint} not set)")
            del providers[name]


# ══════════════════════════════════════════════════════════════════════════════
# Caddy Snippet Generation
# ══════════════════════════════════════════════════════════════════════════════

def generate_caddy_snippets(config):
    """Generate Caddy auth and hooks snippets in /app/caddy.d/."""
    caddy_dir = Path("/app/caddy.d")
    caddy_dir.mkdir(parents=True, exist_ok=True)

    # ── Auth snippet ──────────────────────────────────────────────────────
    auth_password = os.environ.get("AUTH_PASSWORD", "")
    auth_username = os.environ.get("AUTH_USERNAME", "admin")
    if auth_password:
        result = subprocess.run(
            ["caddy", "hash-password", "--plaintext", auth_password],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            bcrypt_hash = result.stdout.strip()
            auth_content = (
                "(auth_block) {\n"
                "    basicauth {\n"
                f"        {auth_username} {bcrypt_hash}\n"
                "    }\n"
                "}\n"
            )
            print("[configure] Caddy auth snippet generated (basicauth enabled)")
        else:
            print(f"[configure] WARNING: caddy hash-password failed: {result.stderr.strip()}")
            auth_content = "(auth_block) {}\n"
    else:
        auth_content = "(auth_block) {}\n"
        print("[configure] Caddy auth snippet: no AUTH_PASSWORD set (no auth)")
    (caddy_dir / "auth.caddyfile").write_text(auth_content)

    # ── Hooks snippet ─────────────────────────────────────────────────────
    hooks_path = get_nested(config, "hooks.path", "/hooks")
    if config.get("hooks", {}).get("enabled"):
        gw_port = os.environ.get("OPENCLAW_GATEWAY_PORT", "18789")
        gw_token = os.environ.get("OPENCLAW_GATEWAY_TOKEN", "")
        hooks_content = (
            f"handle {hooks_path}* {{\n"
            f"    reverse_proxy localhost:{gw_port} {{\n"
            f'        header_up Authorization "Bearer {gw_token}"\n'
            "    }\n"
            "}\n"
        )
        print(f"[configure] Caddy hooks snippet generated (path: {hooks_path})")
    else:
        hooks_content = ""
    (caddy_dir / "hooks.caddyfile").write_text(hooks_content)


# ══════════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════════

def main():
    print("[configure] state dir:", STATE_DIR)
    print("[configure] workspace dir:", WORKSPACE_DIR)
    print("[configure] config file:", CONFIG_FILE)

    # Ensure directories exist
    os.makedirs(STATE_DIR, exist_ok=True)
    os.makedirs(WORKSPACE_DIR, exist_ok=True)

    # ── 1. Load config: custom JSON -> persisted -> empty ─────────────────
    config = {}
    has_custom_config = False

    try:
        with open(CUSTOM_CONFIG) as f:
            config = json.load(f)
        has_custom_config = True
        print("[configure] loaded custom config from", CUSTOM_CONFIG)
    except (FileNotFoundError, json.JSONDecodeError):
        pass

    try:
        with open(CONFIG_FILE) as f:
            persisted = json.load(f)
        deep_merge(config, persisted)
        print("[configure] merged persisted config from", CONFIG_FILE)
    except (FileNotFoundError, json.JSONDecodeError):
        print("[configure] no persisted config found")

    # ── 2. Gateway config ─────────────────────────────────────────────────
    ensure(config, "gateway")

    if os.environ.get("OPENCLAW_GATEWAY_PORT"):
        config["gateway"]["port"] = int(os.environ["OPENCLAW_GATEWAY_PORT"])
    elif not config["gateway"].get("port"):
        config["gateway"]["port"] = 18789

    if not config["gateway"].get("mode"):
        config["gateway"]["mode"] = "local"

    token = os.environ.get("OPENCLAW_GATEWAY_TOKEN", "").strip()
    if token:
        ensure(config, "gateway", "auth")
        config["gateway"]["auth"]["mode"] = "token"
        config["gateway"]["auth"]["token"] = token

    ensure(config, "gateway", "controlUi")
    if config["gateway"]["controlUi"].get("allowInsecureAuth") is None:
        config["gateway"]["controlUi"]["allowInsecureAuth"] = True
    if config["gateway"]["controlUi"].get("enabled") is None:
        config["gateway"]["controlUi"]["enabled"] = True

    # ── 3. Agents defaults ────────────────────────────────────────────────
    ensure(config, "agents", "defaults")
    if not config["agents"]["defaults"].get("workspace"):
        config["agents"]["defaults"]["workspace"] = WORKSPACE_DIR
    ensure(config, "agents", "defaults", "model")

    # ── 4. Custom providers ───────────────────────────────────────────────
    for prov in CUSTOM_PROVIDERS:
        api_key = os.environ.get(prov["env"])
        if api_key:
            print(f"[configure] configuring {prov['key']} provider")
            ensure(config, "models", "providers")
            entry = {
                "api": prov["api"],
                "apiKey": api_key,
                "models": prov["models"],
            }
            # Resolve baseUrl: either static or from env with default
            if "baseUrl" in prov:
                entry["baseUrl"] = prov["baseUrl"]
            elif "baseUrlEnv" in prov:
                url = os.environ.get(prov["baseUrlEnv"], prov["baseUrlDefault"])
                entry["baseUrl"] = url.rstrip("/")
            config["models"]["providers"][prov["key"]] = entry
        else:
            remove_provider(config, has_custom_config, prov["key"],
                            prov["key"].title(), prov["env"])

    # ── 5. Amazon Bedrock (special config) ────────────────────────────────
    if os.environ.get("AWS_ACCESS_KEY_ID") and os.environ.get("AWS_SECRET_ACCESS_KEY"):
        print("[configure] configuring Amazon Bedrock provider")
        ensure(config, "models", "providers")
        region = (os.environ.get("AWS_REGION")
                  or os.environ.get("AWS_DEFAULT_REGION")
                  or "us-east-1")
        config["models"]["providers"]["amazon-bedrock"] = {
            "api": "bedrock-converse-stream",
            "baseUrl": f"https://bedrock-runtime.{region}.amazonaws.com",
            "models": [
                {"id": "anthropic.claude-opus-4-5-20251101-v1:0",
                 "name": "Claude Opus 4.5 (Bedrock)", "contextWindow": 200000},
                {"id": "anthropic.claude-sonnet-4-5-20250929-v1:0",
                 "name": "Claude Sonnet 4.5 (Bedrock)", "contextWindow": 200000},
            ],
        }
        ensure(config, "models")
        config["models"]["bedrockDiscovery"] = {
            "enabled": True,
            "region": region,
            "providerFilter": os.environ.get("BEDROCK_PROVIDER_FILTER", "anthropic"),
            "refreshInterval": 3600,
        }
    else:
        if not has_custom_config:
            providers = get_nested(config, "models.providers")
            if isinstance(providers, dict) and "amazon-bedrock" in providers:
                print("[configure] removing Amazon Bedrock provider (AWS credentials not set)")
                del providers["amazon-bedrock"]
            if isinstance(config.get("models"), dict):
                config["models"].pop("bedrockDiscovery", None)

    # ── 6. Ollama (special config) ────────────────────────────────────────
    ollama_url = os.environ.get("OLLAMA_BASE_URL", "").rstrip("/")
    if ollama_url:
        print("[configure] configuring Ollama provider")
        ensure(config, "models", "providers")
        base = ollama_url if ollama_url.endswith("/v1") else f"{ollama_url}/v1"
        config["models"]["providers"]["ollama"] = {
            "api": "openai-completions",
            "baseUrl": base,
            "models": [
                {"id": "llama3.3", "name": "Llama 3.3", "contextWindow": 128000},
            ],
        }
    else:
        remove_provider(config, has_custom_config, "ollama", "Ollama", "OLLAMA_BASE_URL")

    # ── 7. Clean stale built-in provider entries ──────────────────────────
    # Built-in providers must NOT have models.providers entries.
    opencode_key = (os.environ.get("OPENCODE_API_KEY")
                    or os.environ.get("OPENCODE_ZEN_API_KEY"))

    for env_key, label, provider_key in BUILTIN_PROVIDERS:
        if os.environ.get(env_key):
            print(f"[configure] {label} provider enabled ({env_key} set)")
        if not has_custom_config:
            providers = get_nested(config, "models.providers")
            if isinstance(providers, dict) and provider_key in providers:
                print(f"[configure] removing stale models.providers.{provider_key} (built-in, not needed)")
                del providers[provider_key]

    if opencode_key:
        print("[configure] OpenCode provider enabled (OPENCODE_API_KEY set)")
    if not has_custom_config:
        providers = get_nested(config, "models.providers")
        if isinstance(providers, dict) and "opencode" in providers:
            print("[configure] removing stale models.providers.opencode (built-in, not needed)")
            del providers["opencode"]

    # ── 8. Primary model selection ────────────────────────────────────────
    # Build resolved env lookup for special keys
    resolved_env = dict(os.environ)
    resolved_env["_OPENCODE_KEY"] = opencode_key or ""
    resolved_env["_OLLAMA_URL"] = ollama_url

    if os.environ.get("OPENCLAW_PRIMARY_MODEL"):
        config["agents"]["defaults"]["model"]["primary"] = os.environ["OPENCLAW_PRIMARY_MODEL"]
        print(f"[configure] primary model (override): {os.environ['OPENCLAW_PRIMARY_MODEL']}")
    elif config["agents"]["defaults"]["model"].get("primary"):
        print(f"[configure] primary model (from config): {config['agents']['defaults']['model']['primary']}")
    else:
        for env_key, model in PRIMARY_MODEL_PRIORITY:
            if resolved_env.get(env_key):
                config["agents"]["defaults"]["model"]["primary"] = model
                print(f"[configure] primary model (auto): {model}")
                break

    # ── 9. Deepgram (audio transcription) ─────────────────────────────────
    if os.environ.get("DEEPGRAM_API_KEY"):
        print("[configure] configuring Deepgram transcription (from env)")
        ensure(config, "tools", "media", "audio")
        config["tools"]["media"]["audio"]["enabled"] = True
        config["tools"]["media"]["audio"]["models"] = [
            {"provider": "deepgram", "model": "nova-3"}
        ]
    elif get_nested(config, "tools.media.audio"):
        print("[configure] Deepgram transcription configured (from custom JSON)")

    # ── 10. Channels ──────────────────────────────────────────────────────
    for ch in CHANNELS:
        gate = ch["gate"]
        gate_check = ch.get("gateCheck", "token")

        # Determine if gate is open
        if isinstance(gate, list):
            gate_open = all(os.environ.get(g) for g in gate)
        elif gate_check == "bool":
            val = os.environ.get(gate, "")
            gate_open = val.lower() in ("true", "1")
        else:
            gate_open = bool(os.environ.get(gate))

        if gate_open:
            print(f"[configure] configuring {ch['key']} channel (from env)")
            ensure(config, "channels")

            if ch["merge"]:
                channel_obj = config["channels"].setdefault(ch["key"], {})
            else:
                channel_obj = {}
                config["channels"][ch["key"]] = channel_obj

            channel_obj["enabled"] = True

            # Set token field(s)
            token_field = ch.get("tokenField")
            if token_field:
                if isinstance(gate, list) and isinstance(token_field, list):
                    for g, tf in zip(gate, token_field):
                        channel_obj[tf] = os.environ[g]
                elif isinstance(gate, str) and isinstance(token_field, str):
                    channel_obj[token_field] = os.environ[gate]

            # Apply all declared fields
            apply_fields(channel_obj, ch["fields"])

        elif get_nested(config, f"channels.{ch['key']}"):
            print(f"[configure] {ch['key']} channel configured (from custom JSON)")

    # Clean up empty channels object
    if isinstance(config.get("channels"), dict) and not config["channels"]:
        del config["channels"]

    # ── 11. Browser tool (remote CDP) ─────────────────────────────────────
    if os.environ.get("BROWSER_CDP_URL"):
        print("[configure] configuring browser tool (remote CDP)")
        ensure(config, "browser")
        apply_fields(config["browser"], BROWSER_FIELDS)
    elif config.get("browser"):
        print("[configure] browser configured (from custom JSON)")

    # ── 12. Hooks (webhook automation) ────────────────────────────────────
    hooks_val = os.environ.get("HOOKS_ENABLED", "")
    if hooks_val.lower() in ("true", "1"):
        print("[configure] configuring hooks (from env)")
        ensure(config, "hooks")
        config["hooks"]["enabled"] = True
        apply_fields(config["hooks"], HOOKS_FIELDS)
    elif config.get("hooks"):
        print("[configure] hooks configured (from custom JSON)")

    # ── 13. Convention overrides (OPENCLAW_JSON__*) ───────────────────────
    apply_convention_overrides(config)

    # ── 14. Validate at least one provider ────────────────────────────────
    has_provider = (
        any(os.environ.get(env_key) for env_key, _, _ in BUILTIN_PROVIDERS)
        or bool(opencode_key)
        or bool(os.environ.get("AWS_ACCESS_KEY_ID") and os.environ.get("AWS_SECRET_ACCESS_KEY"))
        or bool(ollama_url)
        or any(os.environ.get(p["env"]) for p in CUSTOM_PROVIDERS)
    )

    if not has_provider:
        print("[configure] ERROR: No AI provider API key set.", file=sys.stderr)
        print("[configure] Providers require an env var -- API keys are never read from the JSON config.", file=sys.stderr)
        print("[configure] Set one of: ANTHROPIC_API_KEY, OPENAI_API_KEY, OPENROUTER_API_KEY, GEMINI_API_KEY,", file=sys.stderr)
        print("[configure]   XAI_API_KEY, GROQ_API_KEY, MISTRAL_API_KEY, CEREBRAS_API_KEY, ZAI_API_KEY,", file=sys.stderr)
        print("[configure]   AI_GATEWAY_API_KEY, OPENCODE_API_KEY, COPILOT_GITHUB_TOKEN, VENICE_API_KEY,", file=sys.stderr)
        print("[configure]   MOONSHOT_API_KEY, KIMI_API_KEY, MINIMAX_API_KEY, SYNTHETIC_API_KEY, XIAOMI_API_KEY,", file=sys.stderr)
        print("[configure]   AWS_ACCESS_KEY_ID+AWS_SECRET_ACCESS_KEY (Bedrock), or OLLAMA_BASE_URL (local)", file=sys.stderr)
        sys.exit(1)

    # ── 15. Write openclaw.json ───────────────────────────────────────────
    os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
    config_json = json.dumps(config, indent=2)
    with open(CONFIG_FILE, "w") as f:
        f.write(config_json)
    os.chmod(CONFIG_FILE, 0o600)
    print("[configure] config written to", CONFIG_FILE)

    # ── 16-17. Generate Caddy snippets ────────────────────────────────────
    generate_caddy_snippets(config)

    print("[configure] done")


if __name__ == "__main__":
    main()
