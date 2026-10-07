# Warsztat repozytorium JARVIS-a

Po ustawieniu JARVIS_REPO_PATH JARVIS może lokalnie obsługiwać repozytorium:

- status repozytorium — status i bieżąca gałąź,
- pokaż gałęzie repo — lista gałęzi,
- utwórz branch test-a — tworzy jarvis/test-a,
- pokaż diff repo — pokazuje zmiany,
- przetestuj repozytorium — compileall i testy unittest,
- wypchnij branch — push tylko po ustawieniu JARVIS_REPO_PUSH_ENABLED=1.

Gałęzie main i master są chronione. Nazwy tworzone przez JARVIS-a dostają
prefiks jarvis/. Operacje używają argumentów procesu, bez shell=True.
Edycja plików jest dostępna przez funkcję lokalnego modułu; panel zapisu
powinien być wystawiony przez Cloudflare dopiero z tokenem administracyjnym.

Panelowe API /api/workspace/* wymaga nagłówka X-Jarvis-Workspace-Token.
Bez JARVIS_WORKSPACE_TOKEN wszystkie endpointy warsztatu zwracają 503.

Tryb pełnego workflow uruchamiają polecenia „zacznij pracę nad repozytorium
<nazwa>” i „zakończ pracę nad repozytorium <opis>”. Druga komenda wykona testy,
utworzy commit, wypchnie branch, a przy JARVIS_GITHUB_AUTO_MERGE=1 utworzy
i scali PR przez GitHub API. Token GitHub jest wyłącznie w lokalnym .env.
Przed scaleniem JARVIS czeka na GitHub Actions; błąd lub timeout pozostawia
PR otwarty i nie zmienia main.
