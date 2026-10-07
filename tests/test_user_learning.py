import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from skills import user_learning


class UserLearningTests(unittest.TestCase):
    def test_aggregates_without_copying_full_question(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(user_learning, "DB_PATH", Path(directory) / "learning.db"):
                user_learning.record_query("Pomóż mi z matematyką i macierzami", route="study", subject="matematyka")
                user_learning.record_query("Wyjaśnij macierze", route="study", subject="matematyka")
                profile = user_learning.profile()
                self.assertEqual(profile["questions"], 2)
                self.assertEqual(profile["subjects"][0]["value"], "matematyka")
                with user_learning._connect() as conn:
                    stored = conn.execute("SELECT keywords FROM query_events").fetchone()[0]
                self.assertNotIn("Pomóż", stored)

    def test_clear_and_command(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(user_learning, "DB_PATH", Path(directory) / "learning.db"):
                user_learning.record_query("Python", subject="programowanie")
                self.assertIn("Na podstawie", user_learning.process_learning_command("czego się nauczyłeś"))
                self.assertIn("Wyczyściłem", user_learning.process_learning_command("wyczyść profil uczenia"))
                self.assertEqual(user_learning.profile()["questions"], 0)


if __name__ == "__main__":
    unittest.main()
