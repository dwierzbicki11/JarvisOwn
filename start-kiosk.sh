#!/bin/bash
set -e
export LIBSEAT_BACKEND=seatd
export XDG_RUNTIME_DIR="/run/user/$(id -u)"
URL="http://127.0.0.1:8765"
echo "Czekam na JARVIS GUI..."
for i in $(seq 1 90); do
    if curl -fsS "$URL/health" >/dev/null 2>&1; then break; fi
    sleep 1
done
BROWSER="$(command -v chromium || true)"
if [ -z "$BROWSER" ]; then BROWSER="$(command -v chromium-browser || true)"; fi
if [ -z "$BROWSER" ]; then echo "Nie znaleziono Chromium."; exit 1; fi
exec dbus-run-session -- cage -- \
    "$BROWSER" \
    --ozone-platform=wayland \
    --enable-features=UseOzonePlatform \
    --kiosk \
    --no-first-run \
    --no-default-browser-check \
    --disable-session-crashed-bubble \
    --disable-infobars \
    --password-store=basic \
    "$URL"
