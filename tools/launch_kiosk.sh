#!/usr/bin/env bash
set -euo pipefail

URL="${JARVIS_KIOSK_URL:-http://127.0.0.1:8765}"
DISPLAY_VALUE="${DISPLAY:-:0}"

export DISPLAY="$DISPLAY_VALUE"
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"

if [[ -S "$XDG_RUNTIME_DIR/wayland-0" ]]; then
    export WAYLAND_DISPLAY="${WAYLAND_DISPLAY:-wayland-0}"
fi

echo "=== JARVIS KIOSK ==="
echo "DISPLAY=$DISPLAY"
echo "URL=$URL"

for attempt in $(seq 1 60)
do
    if curl --fail --silent --max-time 2 "$URL/health" >/dev/null 2>&1; then
        break
    fi

    if [[ "$attempt" -eq 60 ]]; then
        echo "BŁĄD: GUI nie odpowiada pod $URL"
        exit 2
    fi

    sleep 1
done

if command -v chromium >/dev/null 2>&1; then
    exec chromium         --kiosk         --no-first-run         --disable-session-crashed-bubble         --disable-infobars         --disable-translate         --overscroll-history-navigation=0         "$URL"
fi

if command -v chromium-browser >/dev/null 2>&1; then
    exec chromium-browser         --kiosk         --no-first-run         --disable-session-crashed-bubble         --disable-infobars         --disable-translate         --overscroll-history-navigation=0         "$URL"
fi

if command -v firefox-esr >/dev/null 2>&1; then
    exec firefox-esr         --kiosk         "$URL"
fi

if command -v firefox >/dev/null 2>&1; then
    exec firefox         --kiosk         "$URL"
fi

echo "BŁĄD: nie znaleziono Chromium ani Firefoxa."
echo "Zainstaluj np.: sudo apt install chromium"
exit 3
