#!/bin/bash

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)
cd "$SCRIPT_DIR/.."

cleanup() {
    echo "Shutting down..."
    # Kill all background processes in the current process group
    kill $(jobs -p) 2>/dev/null
    # Let the bot stop polling cleanly so a new instance can take over
    wait
    exit "${1:-0}"
}

trap cleanup SIGINT SIGTERM

# Start the FastAPI server
python -m fastapi run src/server.py &
FASTAPI_PID=$!

# Start the bot
python -m src.bot "$@" &
BOT_PID=$!

echo "FastAPI server (PID: $FASTAPI_PID) and Bot (PID: $BOT_PID) started"

# Wait for any process to exit
wait -n
STATUS=$?

# When one process exits, terminate the other one as well and report failure
echo "A process exited with status $STATUS"
cleanup "$((STATUS == 0 ? 1 : STATUS))"
