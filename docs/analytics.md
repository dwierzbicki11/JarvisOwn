# NumPy + Pandas w JARVIS-ie

JARVIS używa NumPy w ścieżce audio: lokalny wake-word oraz lekki voiceprint
pracują na tablicach próbek PCM i cechach widmowych.

Pandas jest warstwą analityczną nad lokalnymi bazami SQLite. Nie zastępuje
SQLite i nie jest ładowany w głównej pętli głosowej. Import Pandas/NumPy w
`skills/analytics.py` jest leniwy, więc koszt pamięci pojawia się dopiero
podczas generowania raportu.

## Źródła danych

- `~/jarvis/data/user_learning.sqlite3` — historia zagregowanych zapytań,
- `~/jarvis/data/jarvis.db` — sesje skupienia/Pomodoro,
- `~/jarvis/data/study_progress.db` — łączna liczba interakcji edukacyjnych.

## Komendy głosowe

Przykłady:

- „Jarvis, jak mi szła nauka w tym tygodniu?”
- „Jarvis, pokaż raport nauki z ostatnich 14 dni.”
- „Jarvis, statystyki nauki z tego miesiąca.”
- „Jarvis, ile czasu się uczyłem?”

Raport podaje liczbę pytań i komend, liczbę i czas sesji skupienia, średni
czas sesji, najczęstsze tematy oraz łączną liczbę zapisanych interakcji
edukacyjnych.

SQLite pozostaje źródłem prawdy. Pandas służy wyłącznie do analizy,
grupowania i przygotowania raportu.
