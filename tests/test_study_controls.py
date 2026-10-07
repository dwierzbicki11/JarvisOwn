import unittest
from skills.study import study_control, study_style_prompt


class StudyControlsTests(unittest.TestCase):
    def test_disable_is_not_enable(self):
        for text in ("wyłącz tryb egzaminu", "wylacz tryb egzaminu", "Koniec egzaminu!"):
            self.assertEqual(study_control(text), ("exam", False))
        self.assertEqual(study_control("włącz tryb egzaminu"), ("exam", True))

    def test_styles(self):
        self.assertEqual(study_control("Tylko naprowadzaj."), ("style", "naprowadzanie"))
        self.assertIn("Nie zdradzaj wyniku", study_style_prompt("naprowadzanie"))
        self.assertIn("jedno pytanie", study_style_prompt("quiz"))

    def test_normal_question_is_not_control(self):
        self.assertIsNone(study_control("co oznacza tryb egzaminu?"))
        self.assertIsNone(study_control("nie wyłącz trybu egzaminu"))


class RouterIntegrationTests(unittest.TestCase):
    def test_controls_update_live_router_state(self):
        import ast
        from pathlib import Path
        tree = ast.parse((Path(__file__).resolve().parents[1] / 'main.py').read_text())
        function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'process_command')
        env = {'english_mode': False, 'exam_mode': True, 'study_style': 'kroki',
               'set_gui_state': lambda *args: None, 'normalize_text': lambda text: text.lower(),
               'study_control': study_control, 'process_flashcard_command': lambda text: None}
        exec(compile(ast.Module(body=[function], type_ignores=[]), 'main.py', 'exec'), env)
        env['process_command']('wyłącz tryb egzaminu')
        self.assertFalse(env['exam_mode'])
        env['process_command']('tylko naprowadzaj')
        self.assertEqual(env['study_style'], 'naprowadzanie')
