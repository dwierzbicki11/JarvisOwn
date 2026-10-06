import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from skills import focus


class FocusTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "jarvis.db"
        self.db_patch = patch.object(
            focus,
            "DB_PATH",
            self.db_path,
        )
        self.db_patch.start()

    def tearDown(self):
        self.db_patch.stop()
        self.tmp.cleanup()

    def test_parse_default_pomodoro(self):
        parsed = focus.parse_focus_start(
            "Pomodoro"
        )

        self.assertEqual(
            parsed["minutes"],
            25,
        )
        self.assertEqual(
            parsed["label"],
            "nauka",
        )

    def test_parse_math_focus(self):
        parsed = focus.parse_focus_start(
            "Zacznij naukę matematyki na 40 minut"
        )

        self.assertEqual(
            parsed["minutes"],
            40,
        )
        self.assertEqual(
            parsed["label"],
            "matematyka",
        )

    def test_start_and_stop_focus(self):
        session = focus.start_focus(
            25,
            label="programowanie",
        )

        self.assertEqual(
            session["minutes"],
            25,
        )

        current = focus.current_focus()

        self.assertIsNotNone(
            current
        )
        self.assertEqual(
            current["label"],
            "programowanie",
        )

        stopped = focus.stop_focus()

        self.assertEqual(
            stopped,
            "programowanie",
        )
        self.assertIsNone(
            focus.current_focus()
        )


if __name__ == "__main__":
    unittest.main()
