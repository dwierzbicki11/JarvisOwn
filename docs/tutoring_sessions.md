# Sesje korepetytora

W panelu JARVIS wybierz **Korepetytor** (`/study`). Wybierz matematykę,
programowanie lub angielski, poziom i tryb nauki. Możesz wpisać konkretny cel,
np. pochodne, pętle w Pythonie lub Present Perfect.

JARVIS zadaje jedno pytanie, czeka na odpowiedź i pokazuje ocenę modelu z
wyjaśnieniem. Następne zadanie pojawia się dopiero po kliknięciu przycisku.
Można poprosić o wskazówkę, pominąć zadanie, wstrzymać sesję lub ją zakończyć.
Wpisany kod jest wyłącznie treścią odpowiedzi — korepetytor go nie wykonuje.

## Polecenia

Te same operacje działają w rozmowie:

- `rozpocznij sesję nauki matematyka`
- `rozpocznij sesję nauki programowanie; quiz; średni; pętle w Pythonie`
- `odpowiedź w sesji: ...` (głosowo dwukropek można pominąć)
- `podpowiedź w sesji`
- `pomiń pytanie w sesji`
- `następne pytanie w sesji`
- `pauza sesji nauki` / `wznów sesję nauki`
- `status sesji nauki` / `historia sesji nauki`
- `koniec sesji nauki`

Tryby to `quiz`, `kroki`, `naprowadzanie`, a poziomy: `podstawowy`, `średni`,
`zaawansowany`. Panel domyślnie wybiera quiz. W rozmowie bez podania trybu
sesja przyjmuje bieżący styl nauki JARVIS-a. Polecenia `tryb quizu`,
`tylko naprowadzaj`, `wyjaśniaj krok po kroku`, `włącz tryb egzaminu`
i `wyłącz tryb egzaminu` zmieniają również trwającą sesję.

Tylko wypowiedzi z prefiksem `odpowiedź w sesji` są oceniane. Możesz nadal
pytać o kalendarz czy pogodę; takie pytania nie zmieniają wyniku sesji.

## Zapis i błędy

Sesje, pytania, odpowiedzi i oceny zapisują się w
`~/jarvis/data/study_sessions.sqlite3`. Pytanie i postęp pozostają po restarcie.
Jednocześnie może istnieć jedna otwarta sesja, także gdy jest wstrzymana.
Zakończenie zachowuje jej historię i pozwala rozpocząć nową.

Oceny `poprawna`, `częściowa` i `błędna` są sugestią modelu, a nie niezależnie
zweryfikowanym pomiarem wiedzy. Niepewna ocena, niepoprawny format odpowiedzi
modelu lub awaria połączenia nie zalicza odpowiedzi jako poprawnej ani błędnej.
Można ponowić odpowiedź. Podpowiedzi i pominięcia mają osobne liczniki.
Spóźniona odpowiedź modelu nie zmienia wstrzymanej ani zakończonej sesji.

Panel odbiera potwierdzenie wykonania polecenia z kolejki. Odświeżenie strony
nie wysyła go ponownie. Po restarcie rdzenia polecenie, którego wyniku nie
zapisano, dostaje komunikat o braku potwierdzenia: sprawdź stan przed ponowieniem.
Nie jest automatycznie odtwarzane, bo mogło już zmienić sesję.

## Model i koszty

Wymagane jest istniejące połączenie z Groq (`GROQ_API_KEY`, `CHAT_MODEL`).
To nie jest tryb nauki całkowicie offline. Generowanie pytania, podpowiedź,
pominięcie i ocena wykonują po jednym żądaniu, z limitem 1600 tokenów wyjścia
i timeoutem 45 sekund, bez automatycznych ponowień. Model otrzymuje tylko
bieżący temat, pytanie, odpowiedź i ograniczoną historię tej sesji.
Panel, historia, status, pauza i wznowienie nie wywołują modelu.

Nie są potrzebne Firebase, Google Cloud, nowa baza w chmurze ani nowe pakiety.
Zużycie istniejącego API zależy od liczby wykonanych działań i planu Groq;
limit pojedynczego żądania nie jest miesięcznym limitem rachunku.

## Aktualizacja

Po pobraniu zmian z `main` uruchom ponownie obie usługi:

```bash
cd ~/jarvis
git pull --ff-only
systemctl --user restart jarvis-core.service jarvis-web.service
```

Otwórz `/study` na swojej domenie. Sprawdź rozpoczęcie sesji, odpowiedź,
pauzę i wznowienie. Testy automatyczne korzystają z tymczasowych baz i
symulowanych odpowiedzi modelu; nie testują mikrofonu, TTS ani jakości ocen
żywego modelu na Raspberry Pi.
