#!/usr/bin/env bash
set -euo pipefail

SOURCE_DIR="${JARVIS_SOURCE_DIR:-$HOME/JarvisOwn}"
RUNTIME_DIR="${JARVIS_RUNTIME_DIR:-$HOME/jarvis}"
USER_SYSTEMD_DIR="$HOME/.config/systemd/user"

echo "=== JARVIS DEPLOY ==="
echo "Repo:    $SOURCE_DIR"
echo "Runtime: $RUNTIME_DIR"

if [[ ! -d "$SOURCE_DIR/.git" ]]; then
    echo "BŁĄD: $SOURCE_DIR nie jest repozytorium Git."
    exit 1
fi

if [[ ! -d "$RUNTIME_DIR" ]]; then
    echo "BŁĄD: brak katalogu runtime $RUNTIME_DIR."
    exit 1
fi

if [[ ! -f "$RUNTIME_DIR/.env" ]]; then
    echo "BŁĄD: brak $RUNTIME_DIR/.env."
    exit 1
fi

PYTHON="$RUNTIME_DIR/.venv/bin/python"

if [[ ! -x "$PYTHON" ]]; then
    echo "BŁĄD: brak virtualenv $RUNTIME_DIR/.venv."
    exit 1
fi

echo
echo "1/7 Aktualizacja repo..."
git -C "$SOURCE_DIR" pull --ff-only

if [[ -n "$(git -C "$SOURCE_DIR" status --porcelain)" ]]; then
    echo "BŁĄD: Repozytorium ma lokalne niezatwierdzone zmiany."
    echo "Deploy przerwany, żeby nie wdrożyć kodu spoza GitHub main."
    git -C "$SOURCE_DIR" status --short
    exit 1
fi

echo
echo "2/7 Kontrola składni w repo..."
"$PYTHON" -m compileall -q     "$SOURCE_DIR/main.py"     "$SOURCE_DIR/jarvis_gui.py"     "$SOURCE_DIR/skills"     "$SOURCE_DIR/tools"     "$SOURCE_DIR/tests"

echo
echo "3/7 Testy regresyjne przed wdrożeniem..."
(
    cd "$SOURCE_DIR"
    PYTHONPATH="$SOURCE_DIR"         "$PYTHON" -m unittest discover -v tests
)

echo
echo "4/7 Synchronizacja kodu..."
rsync -av --delete     --exclude='.git/'     --exclude='.gitignore'     --exclude='.env'     --exclude='.venv/'     --exclude='voices/'     --exclude='data/'     --exclude='runtime/'     --exclude='cache/'     --exclude='study_materials/'     --exclude='__pycache__/'     --exclude='*.pyc'     "$SOURCE_DIR/"     "$RUNTIME_DIR/"

echo
echo "5/7 Aktualizacja usług systemd..."
mkdir -p "$USER_SYSTEMD_DIR"

for unit in     jarvis-core.service     jarvis-web.service     jarvis.target
do
    install -m 0644         "$SOURCE_DIR/systemd/$unit"         "$USER_SYSTEMD_DIR/$unit"
done

chmod +x "$RUNTIME_DIR/wait-audio.sh"
systemctl --user daemon-reload

echo
echo "6/7 Włączanie autostartu po bootowaniu..."

systemctl --user enable     jarvis.target     jarvis-core.service     jarvis-web.service     >/dev/null

if command -v loginctl >/dev/null 2>&1; then
    linger="$(
        loginctl show-user "$USER"             -p Linger             --value 2>/dev/null         || true
    )"

    if [[ "$linger" != "yes" ]]; then
        echo "Włączam linger dla użytkownika $USER..."

        if [[ "$EUID" -eq 0 ]]; then
            loginctl enable-linger "$USER"
        elif command -v sudo >/dev/null 2>&1; then
            sudo loginctl enable-linger "$USER"
        else
            echo "BŁĄD: brak sudo/loginctl — bez linger JARVIS może nie startować po bootowaniu."
            exit 4
        fi
    fi

    linger="$(
        loginctl show-user "$USER"             -p Linger             --value 2>/dev/null         || true
    )"

    if [[ "$linger" != "yes" ]]; then
        echo "BŁĄD: systemd user linger nadal jest wyłączony."
        echo "Uruchom: sudo loginctl enable-linger $USER"
        exit 4
    fi

    echo "systemd user linger: OK"
fi

echo
echo "7/7 Restart JARVIS-a..."
systemctl --user restart jarvis.target

sleep 2

core_state="$(
    systemctl --user is-active jarvis-core.service 2>/dev/null     || true
)"

web_state="$(
    systemctl --user is-active jarvis-web.service 2>/dev/null     || true
)"

enabled_target="$(
    systemctl --user is-enabled jarvis.target 2>/dev/null     || true
)"

enabled_core="$(
    systemctl --user is-enabled jarvis-core.service 2>/dev/null     || true
)"

enabled_web="$(
    systemctl --user is-enabled jarvis-web.service 2>/dev/null     || true
)"

echo
echo "Autostart target: $enabled_target"
echo "Autostart core:   $enabled_core"
echo "Autostart web:    $enabled_web"
echo "Core:             $core_state"
echo "Web:              $web_state"

if [[ "$enabled_target" != "enabled" ]]; then
    echo
    echo "BŁĄD: jarvis.target nie jest włączony do autostartu."
    exit 5
fi

if [[ "$enabled_core" != "enabled" ]]; then
    echo
    echo "BŁĄD: jarvis-core.service nie jest włączony do autostartu."
    exit 5
fi

if [[ "$enabled_web" != "enabled" ]]; then
    echo
    echo "BŁĄD: jarvis-web.service nie jest włączony do autostartu."
    exit 5
fi

if [[ "$core_state" != "active" ]]; then
    echo
    echo "BŁĄD: jarvis-core.service nie działa."
    journalctl --user         -u jarvis-core.service         -n 40         --no-pager || true
    exit 2
fi

if [[ "$web_state" != "active" ]]; then
    echo
    echo "BŁĄD: jarvis-web.service nie działa."
    journalctl --user         -u jarvis-web.service         -n 40         --no-pager || true
    exit 3
fi

if command -v curl >/dev/null 2>&1; then
    if curl         --fail         --silent         --max-time 3         http://127.0.0.1:8765/health         >/dev/null
    then
        echo "GUI/API health: OK"
    else
        echo "UWAGA: GUI działa jako usługa, ale /health jeszcze nie odpowiedział."
    fi
fi

echo
echo "✅ Deploy zakończony."
echo "Log core:"
echo "  journalctl --user -u jarvis-core.service -f"
echo "GUI:"
echo "  http://<IP-RPi>:8765"
