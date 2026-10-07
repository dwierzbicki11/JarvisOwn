"""Bounded, offline Python checks. Never execute or import submitted code."""
import ast
import re

MAX_CODE_CHARS = 12000
MAX_NODES = 4000
COMMAND = re.compile(r"^\s*(?:sprawdź|sprawdz|przeanalizuj)\s+kod\s+python\s*:[ \t]*(?:\r?\n)?", re.I)


def analyze_python(source):
    if len(source) > MAX_CODE_CHARS:
        return "Kod jest za długi. Prześlij fragment do 12000 znaków."
    if not source.strip():
        return "Wklej kod po dwukropku. Zachowaj wcięcia i podziały na linie."
    try:
        tree = ast.parse(source, filename="<kod użytkownika>")
        # compile also checks context errors such as return outside a function.
        # The resulting code object is discarded, never executed.
        if sum(1 for _ in ast.walk(tree)) > MAX_NODES:
            return "Kod jest zbyt złożony. Prześlij mniejszy fragment."
        compile(tree, "<kod użytkownika>", "exec")
    except SyntaxError as exc:
        hint = "Sprawdź składnię w tej linii i bezpośrednio przed nią."
        if isinstance(exc, IndentationError):
            hint = "Sprawdź wcięcia bloku; stosuj spójne odstępy zamiast mieszania tabulatorów i spacji."
        elif "expected ':'" in exc.msg:
            hint = "Po nagłówku bloku, np. if, for lub def, potrzebny jest dwukropek."
        elif "never closed" in exc.msg:
            hint = "Sprawdź, czy każdy otwarty nawias ma pasujący nawias zamykający."
        return f"Błąd składni Pythona: linia {exc.lineno}, kolumna {exc.offset or 1}: {exc.msg}. {hint} Kod nie został uruchomiony."
    except (ValueError, RecursionError, MemoryError):
        return "Nie mogę bezpiecznie przeanalizować tego fragmentu. Skróć kod lub usuń nieprawidłowe znaki."

    warnings = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler) and node.type is None:
            warnings.append((node.lineno, "Ogólne except przechwytuje też przerwanie programu. Rozważ konkretny typ wyjątku."))
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            defaults = [*node.args.defaults, *node.args.kw_defaults]
            if any(isinstance(value, (ast.List, ast.Dict, ast.Set)) for value in defaults):
                warnings.append((node.lineno, "Mutowalny argument domyślny jest współdzielony między wywołaniami. Rozważ None i utworzenie kolekcji wewnątrz funkcji."))
        if isinstance(node, ast.Compare):
            values = [node.left, *node.comparators]
            for index, op in enumerate(node.ops):
                if isinstance(op, (ast.Is, ast.IsNot)) and any(
                    isinstance(value, ast.Constant) and type(value.value) in (str, int, float, bytes)
                    for value in values[index:index + 2]
                ):
                    warnings.append((node.lineno, "Operator is porównuje tożsamość obiektów. Do porównania wartości użyj == lub !=."))
                    break
    warnings = sorted(set(warnings))
    result = "Składnia poprawna. To nie potwierdza poprawności działania ani bezpieczeństwa programu. Kod nie został uruchomiony."
    if warnings:
        result += "\nWskazówki do sprawdzenia:\n" + "\n".join(
            f"Linia {line}: {message}" for line, message in warnings[:6]
        )
        if len(warnings) > 6:
            result += "\nPokazuję pierwszych 6 wskazówek."
    return result


def process_code_command(text):
    match = COMMAND.match(text)
    if not match:
        return None
    source = text[match.end():]
    fenced = re.fullmatch(r"```(?:python|py)?[ \t]*\n(.*?)\n```\s*", source, re.S | re.I)
    if fenced:
        source = fenced.group(1)
    return analyze_python(source)
