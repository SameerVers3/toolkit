# Relay

Local server that speaks the Anthropic Messages API and forwards to Fireworks. Built for Claude Code via `ANTHROPIC_BASE_URL`.

```
Claude Code  <->  relay (:8080)  <->  Fireworks
```

## Run

```bash
.venv/bin/anthropic-relay
```

## Claude Code

```bash
export ANTHROPIC_BASE_URL="http://127.0.0.1:8080"
export ANTHROPIC_API_KEY="fw_your_fireworks_key"
export ANTHROPIC_MODEL="accounts/fireworks/models/kimi-k2p5"
```

`ANTHROPIC_AUTH_TOKEN` works too (Bearer). The relay accepts both.

## Config

Copy `.env.example` to `.env`. 

Useful knobs:

| Var | What |
|-----|------|
| `RELAY_PORT` | Port (default `8080`) |
| `RELAY_PROVIDER` | Upstream (`fireworks`) |
| `FIREWORKS_API_KEY` | Optional server-side key |
| `MODEL_MAP` | `claude-sonnet-4-6=accounts/fireworks/models/...` |
| `RELAY_DEFAULT_MODEL` | Fallback model |

## Endpoints

- `POST /v1/messages`
- `POST /v1/messages/count_tokens`
- `GET /v1/models`
- `GET /health`

## Layout

```
src/relay/
  harnesses/     # client API shape (anthropic currently)
  providers/     # upstreams (fireworks currently)
  transform/     # response field renames
```

Add a provider under `providers/` and `registry.py`. Add a harness under `harnesses/` then mount in `main.py`.
