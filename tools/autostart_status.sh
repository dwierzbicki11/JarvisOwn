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
for unit in     jarvis.target     jarvis-core.service     jarvis-web.service
do
    printf "%-24s " "$unit"
    systemctl --user is-enabled "$unit" 2>/dev/null || true
done

echo
echo "Active:"
for unit in     jarvis.target     jarvis-core.service     jarvis-web.service
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
echo "Ostatnie logi core:"
journalctl --user     -u jarvis-core.service     -n 25     --no-pager || true
