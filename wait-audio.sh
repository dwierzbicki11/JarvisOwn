#!/bin/bash

ENV="/home/zonderq/jarvis/.env"
NAME="Redmi Buds 6 Active"

if [ -f "$ENV" ]; then
    VALUE="$(grep -m1 '^BT_AUDIO_NAME=' "$ENV" | cut -d= -f2-)"
    if [ -n "$VALUE" ]; then
        NAME="$VALUE"
    fi
fi

for i in $(seq 1 30); do
    if wpctl status 2>/dev/null | grep -Fq "$NAME"; then
        exit 0
    fi
    sleep 1
done

# Core i tak spróbuje reconnect w audio_manager.py.
exit 0
