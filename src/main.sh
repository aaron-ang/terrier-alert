#!/bin/bash
# Usage: src/main.sh [--dev]
set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)
cd "$SCRIPT_DIR/.."

if [ "${1:-}" = "--dev" ]; then
    export BOT_ENV=dev
fi

# One process serves the health check, the Telegram webhook and the bot.
# exec hands SIGTERM straight to uvicorn, which shuts the bot down cleanly.
exec python -m uvicorn src.server:main --factory --host 0.0.0.0 --port "${PORT:-8000}"
