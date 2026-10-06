#!/bin/bash
set -u

ENV="/home/zonderq/jarvis/.env"
NAME="Redmi Buds 6 Active"
MAC="24:B2:31:81:7B:05"

if [ -f "$ENV" ]; then
    VALUE="$(grep -m1 '^BT_AUDIO_NAME=' "$ENV" | cut -d= -f2-)"
    [ -n "$VALUE" ] && NAME="$VALUE"

    VALUE="$(grep -m1 '^BT_DEVICE_MAC=' "$ENV" | cut -d= -f2-)"
    [ -n "$VALUE" ] && MAC="$VALUE"
fi

echo "🎧 Czekam na audio Bluetooth: $NAME"

for i in $(seq 1 60); do
    if bluetoothctl info "$MAC" 2>/dev/null | grep -Fq 'Connected: yes'; then
        if wpctl status 2>/dev/null | grep -Fq "$NAME"; then
            echo "🎧 Bluetooth i PipeWire gotowe."
            exit 0
        fi
    else
        # Przy starcie systemu słuchawki mogą być już w zasięgu,
        # ale BlueZ jeszcze ich nie połączył.
        if [ $((i % 5)) -eq 1 ]; then
            bluetoothctl trust "$MAC" >/dev/null 2>&1 || true
            bluetoothctl connect "$MAC" >/dev/null 2>&1 || true
        fi
    fi

    sleep 1
done

echo "⚠️ Audio nie było gotowe po 60 s. Core wystartuje i będzie ponawiał połączenie."
exit 0
