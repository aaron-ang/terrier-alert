#!/bin/bash

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)

python -m fastapi run $SCRIPT_DIR/server.py &

python $(dirname $SCRIPT_DIR)/test/bot.py &

wait -n

exit $?
