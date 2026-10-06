JARVIS v1.3 — głos + AI

Najważniejsze zmiany:
- Redmi Buds 6 Active jako domyślne audio:
  MAC 24:B2:31:81:7B:05
  MIC_TARGET bluez_input.24:B2:31:81:7B:05
- profil HFP/mSBC jest wykrywany i ustawiany dynamicznie,
  bez stałego PipeWire ID typu 97/85/99;
- po reconnect ID mogą się zmienić i JARVIS nadal je znajdzie;
- dłuższy settle po TTS, żeby mikrofon HFP nie gubił początku wypowiedzi;
- odporniejszy router głosowy: lekkie błędy Whispera nie muszą psuć komendy;
- nieznane polecenie trafia do AI (Groq), więc można rozmawiać normalnym językiem;
- lokalne komendy pozostają szybsze: pogoda, czas, zajęcia, status serwera,
  Wi-Fi/RAID, briefing, przypomnienia, Study Mode;
- GUI dalej działa przez LAN na 0.0.0.0:8765, bez HDMI.

Docelowa obsługa:
1. powiedz „Jarvis” / „Hey Jarvis”;
2. po „Tak?” wypowiedz komendę;
3. przez JARVIS_SESSION_SECONDS możesz mówić kolejne komendy bez wake-word;
4. nieznane pytania są obsługiwane przez AI.

Przykłady:
- Jarvis → jaka będzie jutro pogoda?
- Jarvis → jakie mam jutro zajęcia?
- Jarvis → przypomnij mi za 20 minut żeby powtórzyć angielski
- Jarvis → wytłumacz mi pochodną jak na pierwszym roku studiów
- Jarvis → tryb nauki programowania
- Jarvis → status Wi-Fi
- Jarvis → status RAID

Ważne:
RPi jest obecnie na Wi-Fi 5 GHz, co ogranicza konflikt z Bluetooth 2.4 GHz.
Dla HFP/mSBC nie przełączaj Budsów na A2DP, jeśli chcesz używać ich mikrofonu.
