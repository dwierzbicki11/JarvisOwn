#!/bin/bash

ENV="/home/zonderq/jarvis/.env"
MAC="24:B2:31:81:7B:05"
NAME="Redmi Buds 6 Active"

read_env() {
    if [ ! -f "$ENV" ]; then
        return
    fi

    NEW_MAC="$(grep -m1 '^BT_DEVICE_MAC=' "$ENV" | cut -d= -f2-)"
    NEW_NAME="$(grep -m1 '^BT_AUDIO_NAME=' "$ENV" | cut -d= -f2-)"

    [ -n "$NEW_MAC" ] && MAC="$NEW_MAC"
    [ -n "$NEW_NAME" ] && NAME="$NEW_NAME"
}

rfkill unblock bluetooth >/dev/null 2>&1 || true
sleep 2
bluetoothctl power on >/dev/null 2>&1 || true

while true; do
    read_env

    bluetoothctl trust "$MAC" >/dev/null 2>&1 || true

    if ! bluetoothctl info "$MAC" 2>/dev/null |
        grep -q "Connected: yes"; then

        echo "JARVIS BT: łączę $NAME ($MAC)"
        bluetoothctl connect "$MAC" >/dev/null 2>&1 || true
    fi

    sleep 5
done
