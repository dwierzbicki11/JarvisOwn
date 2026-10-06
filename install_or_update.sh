#!/bin/bash
set -euo pipefail

USER_NAME="zonderq"
JARVIS_HOME="/home/$USER_NAME/jarvis"

echo "== JARVIS v1.3 voice/AI headless =="

APT_OPTS=(
  -o Acquire::ForceIPv4=true
  -o Acquire::Retries=5
  -o Acquire::http::Timeout=30
  -o Acquire::https::Timeout=30
)

sudo apt "${APT_OPTS[@]}" update

sudo apt "${APT_OPTS[@]}" install -y \
  ffmpeg \
  alsa-utils \
  pipewire \
  pipewire-pulse \
  wireplumber \
  libspa-0.2-bluetooth \
  bluetooth \
  bluez \
  rfkill \
  iw \
  poppler-utils \
  curl \
  dbus-user-session

cd "$JARVIS_HOME"
source .venv/bin/activate

pip install -U -r requirements.txt
python "$JARVIS_HOME/tools/prepare_wakeword.py"

chmod +x \
  "$JARVIS_HOME/wait-audio.sh" \
  "$JARVIS_HOME/system/jarvis-bluetooth-watch.sh"

sudo install -m 0755 \
  "$JARVIS_HOME/system/jarvis-bluetooth-watch.sh" \
  /usr/local/bin/jarvis-bluetooth-watch.sh

sudo install -m 0644 \
  "$JARVIS_HOME/systemd/jarvis-bluetooth.service" \
  /etc/systemd/system/jarvis-bluetooth.service

mkdir -p "$HOME/.config/systemd/user"

cp \
  "$JARVIS_HOME/systemd/jarvis-core.service" \
  "$HOME/.config/systemd/user/jarvis-core.service"

cp \
  "$JARVIS_HOME/systemd/jarvis-web.service" \
  "$HOME/.config/systemd/user/jarvis-web.service"

sudo systemctl daemon-reload
sudo systemctl enable --now jarvis-bluetooth.service

sudo loginctl enable-linger "$USER_NAME"

systemctl --user daemon-reload
systemctl --user enable jarvis-core.service jarvis-web.service

echo
echo "OK - JARVIS v1.3 zainstalowany."
echo "GUI: http://192.168.1.112:8765"
echo "Audio: profil mSBC ustawiany dynamicznie przez core."
echo "Nie nadpisano .env ani voices/."
echo
echo "Test ręczny:"
echo "  systemctl --user stop jarvis-core.service"
echo "  cd ~/jarvis && source .venv/bin/activate"
echo "  python tools/selftest.py"
echo "  python main.py"
