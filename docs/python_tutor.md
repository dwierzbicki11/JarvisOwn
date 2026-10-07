# Lokalny korepetytor Pythona

W panelu poleceń wpisz (z zachowaniem podziału na linie i wcięć):

```text
sprawdź kod python:
if True
    print("Cześć")
```

JARVIS wskaże linię błędu i zasugeruje sprawdzenie dwukropka.
Akceptuje też polecenie `przeanalizuj kod python:` i blok Markdown
oznaczony `python` lub `py`.

Analiza działa lokalnie na wersji Pythona zainstalowanej na urządzeniu.
Nie wykonuje kodu, nie importuje wskazanych w nim modułów i nie wywołuje LLM.
Limit: 12000 znaków kodu i 4000 węzłów drzewa składniowego.
Poprawna składnia nie oznacza poprawnego wyniku, bezpieczeństwa ani braku
błędów w trakcie działania. Wskazówki dotyczą mutowalnych argumentów
domyślnych, ogólnego `except` i porównywania literałów przez `is`.
To nie jest pełny linter ani obsługa C#/C++.

Na telefonie najlepiej wkleić kod do panelu: dyktowanie zwykle gubi wcięcia.
Analiza kodu jest obsługiwana przed innymi poleceniami, więc tekst wewnątrz
programu nie włącza trybów ani nie usuwa danych JARVIS-a.
