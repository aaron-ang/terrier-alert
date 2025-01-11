#!/bin/bash

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)

python -m fastapi run $SCRIPT_DIR/server.py &

BOT_PROGRAM="$SCRIPT_DIR/bot.py"

python $BOT_PROGRAM $1 &

wait -n

exit $?
