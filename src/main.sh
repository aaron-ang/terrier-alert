#!/bin/bash

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)

cleanup() {
    echo "Received termination signal, shutting down..."
    # Kill all background processes in the current process group
    kill $(jobs -p) 2>/dev/null
    exit 0
}

trap cleanup SIGINT SIGTERM

# Start the FastAPI server
python -m fastapi run $SCRIPT_DIR/server.py &
FASTAPI_PID=$!

# Start the bot
BOT_PROGRAM="$SCRIPT_DIR/bot.py"
python $BOT_PROGRAM $1 &
BOT_PID=$!

echo "FastAPI server (PID: $FASTAPI_PID) and Bot (PID: $BOT_PID) started"

# Wait for any process to exit
wait -n

# When one process exits, terminate the other one as well
cleanup
