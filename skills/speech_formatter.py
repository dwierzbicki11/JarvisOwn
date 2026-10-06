import re


MATH_RE = re.compile(
    r"""
    (
        \\(?:frac|dfrac|tfrac|sqrt|int|iint|iiint|oint|
        sum|prod|lim|sin|cos|tan|tg|cot|log|ln|exp|
        partial|nabla|vec|infty|alpha|beta|gamma|delta|
        theta|lambda|mu|pi|rho|sigma|phi|omega|
        cdot|times|div|pm|leq|geq|neq|approx|begin)
        |
        [∫∑∏√∞≈≠≤≥±×÷∂∇∈∉⊂⊆∪∩→]
        |
        \$[^$]+\$
        |
        \\[\(\[]
        |
        [A-Za-z0-9\)]\s*\^\s*[\{A-Za-z0-9+-]
        |
        [A-Za-z0-9]\s*[=+*/]\s*[A-Za-z0-9\(]
    )
    """,
    re.VERBOSE,
)


def contains_math(text: str) -> bool:
    return bool(
        text
        and MATH_RE.search(text)
    )


def local_math_fallback(text: str) -> str:
    """
    Awaryjna konwersja bez AI.
    Nie rozumie dowolnie złożonego LaTeX,
    ale nie pozwoli Piperowi czytać backslashy i komend.
    """
    s = text

    # Markdown / LaTeX wrappers.
    for token in (
        "```",
        "`",
        "**",
        "__",
        r"\[",
        r"\]",
        r"\(",
        r"\)",
        "$",
    ):
        s = s.replace(token, " ")

    # Ułamki i pierwiastki.
    for _ in range(6):
        old = s

        s = re.sub(
            r"\\(?:dfrac|tfrac|frac)"
            r"\{([^{}]+)\}\{([^{}]+)\}",
            r"\1 przez \2",
            s,
        )

        s = re.sub(
            r"\\sqrt\[([^{}\]]+)\]"
            r"\{([^{}]+)\}",
            r"pierwiastek stopnia \1 z \2",
            s,
        )

        s = re.sub(
            r"\\sqrt\{([^{}]+)\}",
            r"pierwiastek z \1",
            s,
        )

        if s == old:
            break

    replacements = {
        r"\arcsin": "arcus sinus",
        r"\arccos": "arcus cosinus",
        r"\arctan": "arcus tangens",

        r"\sin": "sinus",
        r"\cos": "cosinus",
        r"\tan": "tangens",
        r"\tg": "tangens",
        r"\cot": "cotangens",

        r"\ln": "logarytm naturalny",
        r"\log": "logarytm",
        r"\exp": "eksponenta",

        r"\iiint": "całka potrójna",
        r"\iint": "całka podwójna",
        r"\oint": "całka po konturze",
        r"\int": "całka",

        r"\sum": "suma",
        r"\prod": "iloczyn",
        r"\lim": "granica",

        r"\partial": "pochodna cząstkowa",
        r"\nabla": "nabla",

        r"\infty": "nieskończoność",

        r"\cdot": " razy ",
        r"\times": " razy ",
        r"\div": " podzielone przez ",
        r"\pm": " plus minus ",

        r"\leq": " mniejsze lub równe ",
        r"\geq": " większe lub równe ",
        r"\neq": " różne od ",
        r"\approx": " w przybliżeniu równe ",

        r"\alpha": "alfa",
        r"\beta": "beta",
        r"\gamma": "gamma",
        r"\delta": "delta",
        r"\theta": "theta",
        r"\lambda": "lambda",
        r"\mu": "mi",
        r"\pi": "pi",
        r"\rho": "ro",
        r"\sigma": "sigma",
        r"\phi": "fi",
        r"\omega": "omega",
    }

    for source in sorted(
        replacements,
        key=len,
        reverse=True,
    ):
        s = s.replace(
            source,
            replacements[source],
        )

    # Potęgi.
    s = re.sub(
        r"\^\{?2\}?",
        " do kwadratu",
        s,
    )

    s = re.sub(
        r"\^\{?3\}?",
        " do sześcianu",
        s,
    )

    s = re.sub(
        r"\^\{([^{}]+)\}",
        r" do potęgi \1",
        s,
    )

    s = re.sub(
        r"\^([A-Za-z0-9+-]+)",
        r" do potęgi \1",
        s,
    )

    # Indeksy.
    s = re.sub(
        r"_\{([^{}]+)\}",
        r" z indeksem \1",
        s,
    )

    s = re.sub(
        r"_([A-Za-z0-9+-]+)",
        r" z indeksem \1",
        s,
    )

    unicode_symbols = {
        "=": " równa się ",
        "≤": " mniejsze lub równe ",
        "≥": " większe lub równe ",
        "≠": " różne od ",
        "≈": " w przybliżeniu równe ",
        "±": " plus minus ",
        "×": " razy ",
        "÷": " podzielone przez ",
        "∞": " nieskończoność ",
        "∈": " należy do ",
        "∉": " nie należy do ",
        "∪": " suma zbiorów ",
        "∩": " część wspólna ",
        "→": " dąży do ",
    }

    for symbol, word in unicode_symbols.items():
        s = s.replace(
            symbol,
            word,
        )

    # Pozostałości konstrukcji LaTeX.
    s = re.sub(
        r"\\(?:left|right|quad|qquad)",
        " ",
        s,
    )

    s = s.replace("{", " ")
    s = s.replace("}", " ")
    s = s.replace("\\", " ")

    return re.sub(
        r"\s+",
        " ",
        s,
    ).strip()


def speechify_math(
    text: str,
    *,
    client=None,
    model=None,
) -> str:
    """
    Zamienia matematyczny tekst ekranowy
    na naturalną wypowiedź.

    Zwykły tekst nie wykonuje dodatkowego requestu.
    """

    if not contains_math(text):
        return text

    if client is not None and model:
        try:
            response = client.chat.completions.create(
                model=model,
                temperature=0.0,
                max_tokens=1000,
                messages=[
                    {
                        "role": "system",
                        "content": """
Jesteś warstwą Math-to-Speech dla asystenta głosowego JARVIS.

Dostaniesz tekst przeznaczony również do wyświetlenia użytkownikowi.
Może zawierać LaTeX, Markdown i wyrażenia matematyczne.

Twoim jedynym zadaniem jest przepisać ten sam tekst do naturalnej mowy.

ZASADY:
- zachowaj dokładnie znaczenie matematyczne,
- niczego nie rozwiązuj,
- nie poprawiaj wyniku,
- niczego nie dodawaj,
- zachowaj język oryginalnej odpowiedzi,
- usuń wizualną składnię LaTeX i Markdown,
- nigdy nie wypowiadaj słów typu:
  frac, sqrt, begin, end, left, right, backslash,
  klamra, dolar, nawias kwadratowy LaTeX.

Czytaj matematykę semantycznie.

Przykłady zasad:
x^2 -> x do kwadratu
x^3 -> x do sześcianu
x^n -> x do potęgi n

a/b -> a przez b

sqrt(x) -> pierwiastek z x

sqrt[n](x) ->
pierwiastek stopnia n z x

sin(x) -> sinus x
cos(x) -> cosinus x
tan(x) -> tangens x

ln(x) ->
logarytm naturalny z x

log_a(x) ->
logarytm przy podstawie a z x

f'(x) ->
pochodna funkcji f w punkcie x

d/dx f(x) ->
pochodna funkcji f względem x

partial f / partial x ->
pochodna cząstkowa funkcji f względem x

lim x->0 ->
granica, gdy x dąży do zera

int f(x) dx ->
całka z f od x, względem x

Całki oznaczone muszą zawierać
dolną i górną granicę.

Sumy i iloczyny muszą zawierać
zakres indeksu.

Macierze czytaj wierszami.

Wektory nazywaj wektorami.

Symbole greckie czytaj ich nazwami.

Relacje:
=  -> równa się
!= -> różne od
<  -> mniejsze od
>  -> większe od
<= -> mniejsze lub równe
>= -> większe lub równe

Jeśli złożone nawiasy są niezbędne do
jednoznacznego przeczytania wyrażenia,
powiedz:
"otwieram nawias"
i
"zamykam nawias".

Zwróć WYŁĄCZNIE tekst gotowy
do syntezatora mowy.
""".strip(),
                    },
                    {
                        "role": "user",
                        "content": text,
                    },
                ],
            )

            spoken = (
                response
                .choices[0]
                .message
                .content
                .strip()
            )

            if spoken:
                # Gdyby model mimo instrukcji zostawił
                # fragment LaTeX, doczyść go lokalnie.
                if contains_math(spoken):
                    spoken = local_math_fallback(
                        spoken
                    )

                return spoken

        except Exception as exc:
            print(
                f"[MATH SPEECH] AI fallback: {exc}",
                flush=True,
            )

    return local_math_fallback(text)
