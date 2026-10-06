#!/usr/bin/env bash
set -euo pipefail

RUNTIME_DIR="${JARVIS_RUNTIME_DIR:-$HOME/jarvis}"
SOURCE_DIR="${JARVIS_SOURCE_DIR:-$HOME/JarvisOwn}"
USER_SYSTEMD_DIR="$HOME/.config/systemd/user"

echo "=== JARVIS AUTOSTART ==="
echo "Runtime: $RUNTIME_DIR"
echo "Repo:    $SOURCE_DIR"

if [[ ! -f "$RUNTIME_DIR/main.py" ]]; then
    echo "BŁĄD: brak $RUNTIME_DIR/main.py"
    echo "Najpierw wdroż repo do katalogu runtime."
    exit 1
fi

if [[ ! -x "$RUNTIME_DIR/.venv/bin/python" ]]; then
    echo "BŁĄD: brak $RUNTIME_DIR/.venv/bin/python"
    exit 1
fi

if [[ ! -x "$RUNTIME_DIR/.venv/bin/uvicorn" ]]; then
    echo "BŁĄD: brak $RUNTIME_DIR/.venv/bin/uvicorn"
    exit 1
fi

if [[ ! -f "$RUNTIME_DIR/.env" ]]; then
    echo "BŁĄD: brak $RUNTIME_DIR/.env"
    exit 1
fi

mkdir -p "$USER_SYSTEMD_DIR"

install -m 0644     "$SOURCE_DIR/systemd/jarvis-core.service"     "$USER_SYSTEMD_DIR/jarvis-core.service"

install -m 0644     "$SOURCE_DIR/systemd/jarvis-web.service"     "$USER_SYSTEMD_DIR/jarvis-web.service"

install -m 0644     "$SOURCE_DIR/systemd/jarvis-kiosk.service"     "$USER_SYSTEMD_DIR/jarvis-kiosk.service"

install -m 0644     "$SOURCE_DIR/systemd/jarvis.target"     "$USER_SYSTEMD_DIR/jarvis.target"

chmod +x "$RUNTIME_DIR/wait-audio.sh"
chmod +x "$RUNTIME_DIR/tools/launch_kiosk.sh"

systemctl --user daemon-reload

# Target uruchamia zarówno main.py, jak i stronę WWW.
# Włączamy też obie usługi osobno jako dodatkowe zabezpieczenie bootu.
systemctl --user enable     jarvis.target     jarvis-core.service     jarvis-web.service     jarvis-kiosk.service     >/dev/null

# User systemd musi żyć również bez aktywnego logowania po restarcie RPi.
if command -v loginctl >/dev/null 2>&1; then
    linger="$(
        loginctl show-user "$USER"             -p Linger             --value 2>/dev/null         || true
    )"

    if [[ "$linger" != "yes" ]]; then
        echo
        echo "Włączam systemd user manager przy starcie systemu (linger)..."

        if [[ "$EUID" -eq 0 ]]; then
            loginctl enable-linger "$USER"
        elif command -v sudo >/dev/null 2>&1; then
            sudo loginctl enable-linger "$USER"
        else
            echo "BŁĄD: brak sudo. Uruchom:"
            echo "  sudo loginctl enable-linger $USER"
            exit 4
        fi
    fi

    linger="$(
        loginctl show-user "$USER"             -p Linger             --value 2>/dev/null         || true
    )"

    if [[ "$linger" != "yes" ]]; then
        echo "BŁĄD: linger nadal jest wyłączony."
        exit 4
    fi
fi

systemctl --user restart jarvis.target

echo
echo "Status targetu:"
systemctl --user --no-pager --full status jarvis.target || true

echo
echo "Core:"
systemctl --user --no-pager --full status jarvis-core.service || true

echo
echo "Web:"
systemctl --user --no-pager --full status jarvis-web.service || true

echo
echo "Kiosk:"
systemctl --user --no-pager --full status jarvis-kiosk.service || true

echo
echo "Gotowe."
echo "JARVIS main.py, GUI i lokalny kiosk będą uruchamiane automatycznie po starcie RPi."
echo "GUI: http://<IP-RPi>:8765"
