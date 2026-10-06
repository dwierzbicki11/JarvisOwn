JARVIS v1.2 - 2026-10-06

GŁÓWNE ZMIANY
1. Rozpoznawanie głosu:
   - openWakeWord działa lokalnie w czuwaniu,
   - wieloklatkowe potwierdzanie wake-word ogranicza fałszywe aktywacje,
   - opcjonalny Speex noise suppression z fallbackiem,
   - WebRTC VAD + adaptacyjny RMS,
   - krótsza cisza kończąca wypowiedź,
   - filtr typowych halucynacji Whispera,
   - diagnostyka opóźnień VAD/Whisper/Groq/Piper.

2. Nauka:
   - folder ~/jarvis/study_materials,
   - PDF/TXT/MD/C/C++/C#/Python/Java,
   - komendy:
       "Jakie mam materiały?"
       "Ucz mnie z <nazwa pliku>"
       "Przepytaj mnie z <nazwa pliku>"
   - PDF jest wyciągany przez pdftotext i cache'owany.

3. Organizacja:
   - lokalna pamięć SQLite,
   - przypomnienia,
   - powiadomienie o zbliżających się zajęciach,
   - Study Mode i Exam Mode.

4. Web GUI:
   - działa na 0.0.0.0:8765,
   - nie wymaga HDMI,
   - pokazuje latency,
   - pokazuje Wi-Fi i RAID,
   - pokazuje przypomnienia,
   - ma pole tekstowe: polecenie z przeglądarki trafia do JARVIS core.

5. System:
   - diagnostyka Wi-Fi / RAID,
   - Bluetooth autoreconnect,
   - headless - Cage/Chromium nie są uruchamiane automatycznie.

INSTALACJA / AKTUALIZACJA

Najpierw zachowaj swój .env i voices:
  cp -a ~/jarvis ~/jarvis.backup-before-v1.2

Skopiuj pakiet v1.2 do ~/jarvis zachowując:
  - ~/jarvis/.env
  - ~/jarvis/voices/

Następnie:
  cd ~/jarvis
  source .venv/bin/activate
  ./install_or_update.sh

Dopisz do .env brakujące wpisy z .env.example.
Nie usuwaj GROQ_API_KEY ani PK_CALENDAR_ICS_URL.

TEST:
  cd ~/jarvis
  source .venv/bin/activate
  python -m py_compile main.py jarvis_gui.py skills/*.py tools/*.py
  python tools/selftest.py

DIAGNOSTYKA MIKROFONU:
  systemctl --user stop jarvis-core.service
  python tools/audio_diagnostics.py

TEST RĘCZNY CORE:
  python main.py

Po teście:
  systemctl --user restart jarvis-core.service
  systemctl --user restart jarvis-web.service

GUI:
  http://192.168.1.112:8765

LOG:
  journalctl --user -u jarvis-core.service -f

MATERIAŁY DO NAUKI:
  mkdir -p ~/jarvis/study_materials
  cp wykład.pdf ~/jarvis/study_materials/

Przykłady:
  "Jarvis"
  "Jakie mam materiały?"
  "Ucz mnie z wykład"
  "Przepytaj mnie z wykład"
  "Tryb nauki matematyki"
  "Tryb egzaminu"
  "Przypomnij mi za 20 minut żeby powtórzyć angielski"
  "Status Wi-Fi"
  "Status RAID"

UWAGA O HDMI:
Na tym RPi podłączenie HDMI mocno pogarszało Wi-Fi 2.4 GHz.
v1.2 jest więc skonfigurowany jako headless + GUI przez LAN.
