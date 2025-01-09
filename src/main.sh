#!/bin/bash

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)

python -m fastapi run $SCRIPT_DIR/server.py &

if [ "$1" == "--test" ]; then
    BOT_PROGRAM="$(dirname $SCRIPT_DIR)/test/bot.py"
else
    BOT_PROGRAM="$SCRIPT_DIR/bot.py"
fi

python $BOT_PROGRAM &

wait -n

exit $?
