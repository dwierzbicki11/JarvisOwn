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
