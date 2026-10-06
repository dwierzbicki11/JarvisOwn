JARVIS - skonsolidowana wersja 2026-10-06

ZAWIERA
- lokalny wake-word openWakeWord przed Whisperem,
- WebRTC VAD z filtrem trzasków/stuknięć,
- szybszy koniec wypowiedzi (0.8 s),
- jednorazową kalibrację RMS,
- Groq Whisper large-v3,
- Piper ładowany raz do RAM,
- dynamiczne wyszukiwanie sinka AP721113,
- sleep / standby / shutdown,
- GUI FastAPI + Chromium/Cage,
- stan GUI: CZUWANIE / SŁUCHAM / MYŚLĘ / MÓWIĘ / UŚPIENIE,
- Bluetooth autoreconnect,
- Google Calendar PK,
- GTFS Kraków,
- Garlica Duchowna Kapliczka -> AKF / PK,
- cache ciężkiego route_planner,
- Study Mode dla matematyki/programowania/angielskiego,
- pomiar opóźnień VAD / Whisper / Groq / Piper / GTFS.

WAŻNE
1. Zachowaj istniejący ~/jarvis/.env.
   .env.example nie zawiera Twojego klucza Groq ani tajnego URL kalendarza.

2. Nie używamy SpeechRecognition.
   standby -> openWakeWord
   aktywny -> WebRTC VAD -> Groq Whisper -> router/Groq -> Piper

3. Przed podmianą:
   cp -a ~/jarvis ~/jarvis.backup-2026-10-06

4. Po skopiowaniu plików:
   cd ~/jarvis
   source .venv/bin/activate
   pip install -U -r requirements.txt
   python -c "import openwakeword; openwakeword.utils.download_models(['hey_jarvis'])"

5. Walidacja:
   python -m py_compile \
     main.py jarvis_gui.py \
     skills/speech_vad.py \
     skills/local_wakeword.py \
     skills/weather.py \
     skills/pk_calendar.py \
     skills/krakow_transport.py \
     skills/route_planner.py \
     skills/study.py

6. Test ręczny:
   systemctl --user stop jarvis-core.service
   python ~/jarvis/main.py

7. Po teście:
   systemctl --user start jarvis-core.service

8. Log:
   journalctl --user -u jarvis-core.service -f

9. GUI API:
   curl http://127.0.0.1:8765/health

10. Cage/seatd:
    sudo systemctl enable --now seatd
    ls -l /run/seatd.sock
    użytkownik musi należeć do grupy socketu seatd oraz video/render.
    Po dodaniu grup wykonaj reboot.

11. Autologin tty1 i ~/.bash_profile:
    szablony są w config/.
    install_or_update.sh celowo ich nie nadpisuje.
