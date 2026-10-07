import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from skills import study_progress


class StudyProgressTests(unittest.TestCase):
    def test_records_and_formats_subject_activity(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(study_progress, "DB_PATH", Path(directory) / "progress.db"):
                study_progress.record_interaction("matematyka")
                study_progress.record_interaction("matematyka")
                study_progress.record_interaction("programowanie")
                result = study_progress.format_summary()
                self.assertIn("matematyka: 2 interakcje", result)
                self.assertIn("programowanie: 1 interakcja", result)

    def test_empty_tracker_has_clear_status(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(study_progress, "DB_PATH", Path(directory) / "progress.db"):
                self.assertEqual(
                    study_progress.format_summary(),
                    "Nie mam jeszcze zapisanej aktywności nauki.",
                )


if __name__ == "__main__":
    unittest.main()

