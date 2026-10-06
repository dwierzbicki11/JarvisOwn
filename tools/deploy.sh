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

if [[ ! -x "$RUNTIME_DIR/.venv/bin/python" ]]; then
    echo "BŁĄD: brak virtualenv $RUNTIME_DIR/.venv."
    exit 1
fi

echo
echo "1/6 Aktualizacja repo..."
git -C "$SOURCE_DIR" pull --ff-only

echo
echo "2/6 Synchronizacja kodu..."
rsync -av --delete     --exclude='.git/'     --exclude='.gitignore'     --exclude='.env'     --exclude='.venv/'     --exclude='voices/'     --exclude='data/'     --exclude='runtime/'     --exclude='cache/'     --exclude='study_materials/'     --exclude='__pycache__/'     --exclude='*.pyc'     "$SOURCE_DIR/"     "$RUNTIME_DIR/"

echo
echo "3/6 Aktualizacja usług systemd..."
mkdir -p "$USER_SYSTEMD_DIR"

for unit in     jarvis-core.service     jarvis-web.service     jarvis.target
do
    install -m 0644         "$SOURCE_DIR/systemd/$unit"         "$USER_SYSTEMD_DIR/$unit"
done

systemctl --user daemon-reload

echo
echo "4/6 Kontrola składni..."
"$RUNTIME_DIR/.venv/bin/python"     -m compileall -q     "$RUNTIME_DIR/main.py"     "$RUNTIME_DIR/jarvis_gui.py"     "$RUNTIME_DIR/skills"     "$RUNTIME_DIR/tools"     "$RUNTIME_DIR/tests"

echo
echo "5/6 Testy regresyjne..."
(
    cd "$RUNTIME_DIR"
    "$RUNTIME_DIR/.venv/bin/python"         -m unittest discover -v tests
)

echo
echo "6/6 Restart JARVIS-a..."
systemctl --user enable jarvis.target >/dev/null 2>&1 || true
systemctl --user restart jarvis.target

sleep 2

core_state="$(
    systemctl --user is-active jarvis-core.service 2>/dev/null     || true
)"

web_state="$(
    systemctl --user is-active jarvis-web.service 2>/dev/null     || true
)"

echo
echo "Core: $core_state"
echo "Web:  $web_state"

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
