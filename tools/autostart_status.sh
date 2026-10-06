#!/usr/bin/env bash
set -u

echo "=== JARVIS AUTOSTART STATUS ==="

echo
echo "Linger:"
if command -v loginctl >/dev/null 2>&1; then
    loginctl show-user "$USER" -p Linger || true
else
    echo "loginctl niedostępny"
fi

echo
echo "Enabled:"
for unit in     jarvis.target     jarvis-core.service     jarvis-web.service     jarvis-kiosk.service
do
    printf "%-24s " "$unit"
    systemctl --user is-enabled "$unit" 2>/dev/null || true
done

echo
echo "Active:"
for unit in     jarvis.target     jarvis-core.service     jarvis-web.service     jarvis-kiosk.service
do
    printf "%-24s " "$unit"
    systemctl --user is-active "$unit" 2>/dev/null || true
done

echo
echo "Proces main.py:"
pgrep -af "/home/zonderq/jarvis/main.py" || true

echo
echo "Proces GUI:"
pgrep -af "uvicorn jarvis_gui:app" || true

echo
echo "Proces kiosku:"
pgrep -af "chromium.*127.0.0.1:8765|firefox.*127.0.0.1:8765" || true

echo
echo "Ostatnie logi core:"
journalctl --user     -u jarvis-core.service     -n 25     --no-pager || true


echo
echo "Bluetooth:"
if command -v bluetoothctl >/dev/null 2>&1; then
    MAC="$(
        grep -m1 '^BT_DEVICE_MAC=' /home/zonderq/jarvis/.env 2>/dev/null         | cut -d= -f2-
    )"

    if [ -n "$MAC" ]; then
        bluetoothctl info "$MAC" 2>/dev/null             | grep -E 'Name:|Connected:|Battery|Percentage'             || true
    else
        echo "Brak BT_DEVICE_MAC w .env"
    fi
fi

echo
echo "PipeWire:"
wpctl status 2>/dev/null     | grep -E 'Redmi Buds|bluez_input|bluez_output'     || echo "Nie znaleziono skonfigurowanych słuchawek w PipeWire."

echo
echo "Plik logu core:"
LOG="/home/zonderq/jarvis/runtime/jarvis-core.log"

if [ -f "$LOG" ]; then
    tail -n 40 "$LOG"
else
    echo "Brak $LOG"
fi
