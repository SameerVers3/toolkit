# Relay

Local server that speaks the Anthropic Messages API and forwards to Fireworks. Built for Claude Code via `ANTHROPIC_BASE_URL`.

```
Claude Code  <->  relay (:8080)  <->  Fireworks
```

## Setup

```bash
python -m venv .venv
source .venv/bin/activate.fish   # bash: source .venv/bin/activate
pip install -e .
cp .env.example .env
```

Or skip this and use `./scripts/claude-code` / `tkr-claude-code`, which handles venv + install for you.

## Run

```bash
.venv/bin/anthropic-relay
```

## Claude Code

Manual exports:

```bash
export ANTHROPIC_BASE_URL="http://127.0.0.1:8080"
export ANTHROPIC_AUTH_TOKEN="fw_your_fireworks_key"
export ANTHROPIC_MODEL="claude-sonnet-4-6"
unset ANTHROPIC_API_KEY
```

Use a Claude-looking model id in Claude Code. Map it to Fireworks via `MODEL_MAP` in `.env`. Don't set both `ANTHROPIC_API_KEY` and `ANTHROPIC_AUTH_TOKEN`.

### Launcher (`scripts/claude-code`)

Prompts for the exports above, saves them to `~/.config/toolkit/.relay-env`, ensures the venv/package, starts the relay if needed, then opens Claude Code. Installs itself on PATH as `tkr-claude-code`.

```bash
./scripts/claude-code          # from the repo
tkr-claude-code                # from anywhere (after first run)
tkr-claude-code .              # open Claude Code in the current directory
tkr-claude-code /path/to/proj  # open Claude Code in that project
```

A directory argument (like `.`) is treated as the working directory, Claude Code is started there. Extra args are forwarded to `claude`.

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
