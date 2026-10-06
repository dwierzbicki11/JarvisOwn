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

install -m 0644     "$SOURCE_DIR/systemd/jarvis.target"     "$USER_SYSTEMD_DIR/jarvis.target"

chmod +x "$RUNTIME_DIR/wait-audio.sh"

systemctl --user daemon-reload

# Target uruchamia zarówno main.py, jak i stronę WWW.
systemctl --user enable --now jarvis.target

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
            echo "UWAGA: brak sudo. Uruchom jako root:"
            echo "  loginctl enable-linger $USER"
        fi
    fi
fi

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
echo "Gotowe."
echo "JARVIS main.py i GUI będą uruchamiane automatycznie po starcie RPi."
echo "GUI: http://<IP-RPi>:8765"
