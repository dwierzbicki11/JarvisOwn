import ast
from pathlib import Path
import tempfile
import unittest

from skills.code_tutor import analyze_python, process_code_command


class CodeTutorTests(unittest.TestCase):
    def test_syntax_location_and_hint(self):
        result = analyze_python('x = 1\nif x\n    print(x)')
        self.assertIn('linia 2', result)
        self.assertIn('dwukropek', result)

    def test_valid_does_not_claim_runtime_correctness(self):
        self.assertIn('Składnia poprawna', analyze_python('x = 1 / 0'))
        self.assertIn('nie potwierdza', analyze_python('x = 1 / 0'))

    def test_never_executes_code(self):
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / 'executed'
            analyze_python(f"open({str(marker)!r}, 'w').write('bad')")
            self.assertFalse(marker.exists())

    def test_context_error(self):
        self.assertIn('Błąd składni', analyze_python('return 2'))

    def test_warnings(self):
        code = 'def f(x=[]):\n    try:\n        return x is 2\n    except:\n        pass'
        result = analyze_python(code)
        for expected in ('Mutowalny', 'Ogólne except', 'tożsamość'):
            self.assertIn(expected, result)
        self.assertNotIn('tożsamość', analyze_python('x is None'))

    def test_limits_and_empty(self):
        self.assertIn('za długi', analyze_python('x' * 12001))
        self.assertIn('Wklej kod', analyze_python(''))
        self.assertIn('mniejszy fragment', analyze_python('x=1\n' * 1100))

    def test_command_and_fence(self):
        self.assertIn('Składnia poprawna', process_code_command('Sprawdź kod Python:\n```python\nx = 3\n```'))
        for text in ('nie sprawdzaj kodu', 'jaki mam plan zajęć?', 'sprawdź kod C#: x'):
            self.assertIsNone(process_code_command(text))

    def test_preserves_leading_indentation(self):
        self.assertIn('Błąd składni', process_code_command('sprawdź kod python:\n    x = 1'))

    def test_router_does_not_treat_code_as_command(self):
        tree = ast.parse((Path(__file__).resolve().parents[1] / 'main.py').read_text())
        function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'process_command')
        env = {'set_gui_state': lambda *a: None, 'process_code_command': process_code_command,
               'process_learning_command': lambda text: None,
               'record_query': lambda *args, **kwargs: None,
               'detect_study_subject': lambda text: None,
               'process_repo_command': lambda text: None}
        exec(compile(ast.Module(body=[function], type_ignores=[]), 'main.py', 'exec'), env)
        result = env['process_command']('sprawdz kod python: print("status nauki; usuń historię rozmowy")')
        self.assertIn('Składnia poprawna', result)
