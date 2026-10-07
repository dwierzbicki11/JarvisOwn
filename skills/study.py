def detect_study_subject(text: str):
    lower = text.lower()

    if any(
        word in lower
        for word in (
            "matem", "pochodn", "całk", "macierz",
            "funkcj", "równan", "algebra",
        )
    ):
        return "matematyka"

    if any(
        word in lower
        for word in (
            "program", "kod", "c#", "c++", "python",
            "java", "algorytm", "debug",
        )
    ):
        return "programowanie"

    if any(
        word in lower
        for word in (
            "angiel", "english", "grammar",
            "vocabulary", "słówk", "wymow",
        )
    ):
        return "angielski"

    return None


def study_prompt(subject=None):
    base = (
        "Jesteś również korepetytorem użytkownika. "
        "Pomagasz mu uczyć się aktywnie, a nie tylko podajesz odpowiedzi. "
        "Gdy rozwiązuje zadanie, najpierw wyjaśnij ideę i kolejne kroki. "
        "Jeżeli prosi, aby go tylko naprowadzać, nie zdradzaj wyniku. "
        "Możesz tworzyć krótkie quizy i sprawdzać jego odpowiedzi. "
    )

    if subject == "matematyka":
        return base + (
            "W matematyce zapisuj tok rozwiązania jasno i krok po kroku. "
            "Kontroluj rachunki i pokazuj, skąd wynika użyty wzór."
        )

    if subject == "programowanie":
        return base + (
            "W programowaniu skupiaj się na zrozumieniu kodu, debugowaniu, "
            "algorytmach i dobrych praktykach. "
            "Domyślnie pokazuj małe, konkretne przykłady."
        )

    if subject == "angielski":
        return base + (
            "W angielskim prowadź naturalną rozmowę. "
            "Nie przerywaj po każdym drobnym błędzie; po wypowiedzi wskaż "
            "najważniejsze błędy i lepszą wersję zdania."
        )

    return base


STUDY_STYLES = {
    "kroki": "Wyjaśniaj krok po kroku i sprawdzaj zrozumienie.",
    "naprowadzanie": "Nie zdradzaj wyniku. Podaj jedną wskazówkę i poczekaj na odpowiedź użytkownika.",
    "quiz": "Zadaj jedno pytanie naraz. Poczekaj na odpowiedź, oceń ją i wyjaśnij błędy przed kolejnym pytaniem.",
}


def study_control(text):
    """Exact controls prevent a disable command from matching enable."""
    import re
    import unicodedata
    text = unicodedata.normalize("NFKD", text.lower().replace("ł", "l"))
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"\s+", " ", text).strip().rstrip(".!?")
    return {
        "tryb egzaminu": ("exam", True),
        "wlacz tryb egzaminu": ("exam", True),
        "wylacz tryb egzaminu": ("exam", False),
        "koniec egzaminu": ("exam", False),
        "tylko naprowadzaj": ("style", "naprowadzanie"),
        "nie podawaj wyniku": ("style", "naprowadzanie"),
        "tryb quizu": ("style", "quiz"),
        "wyjasniaj krok po kroku": ("style", "kroki"),
    }.get(text)


def study_style_prompt(style):
    return STUDY_STYLES.get(style, STUDY_STYLES["kroki"])
