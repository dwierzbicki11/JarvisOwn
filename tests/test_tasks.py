import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from skills import tasks


class TaskTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "jarvis.db"
        self.db_patch = patch.object(tasks, "DB_PATH", self.db_path)
        self.db_patch.start()

    def tearDown(self):
        self.db_patch.stop()
        self.tmp.cleanup()

    def test_add_and_complete_task(self):
        task_id = tasks.add_task("zrobić sprawozdanie")
        self.assertIsNotNone(task_id)
        pending = tasks.pending_tasks()
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["text"], "zrobić sprawozdanie")
        completed = tasks.complete_latest()
        self.assertEqual(completed, "zrobić sprawozdanie")
        self.assertEqual(tasks.pending_tasks(), [])

    def test_parse_tomorrow_task(self):
        parsed = tasks.parse_task_command(
            "Dodaj zadanie na jutro o 18:30 zrobić sprawozdanie"
        )
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["text"], "zrobić sprawozdanie")
        self.assertIsNotNone(parsed["due_at"])
        self.assertEqual(parsed["due_at"].hour, 18)
        self.assertEqual(parsed["due_at"].minute, 30)

    def test_parse_priority_task(self):
        parsed = tasks.parse_task_command(
            "Dodaj pilne zadanie wysłać projekt"
        )
        self.assertTrue(parsed["priority"])
        self.assertEqual(parsed["text"], "wysłać projekt")

    def test_due_notice_only_once(self):
        due = datetime.now(tasks.TIMEZONE)
        tasks.add_task("wysłać raport", due_at=due, priority=True)
        first = tasks.pop_due_task_notices(horizon_minutes=30)
        second = tasks.pop_due_task_notices(horizon_minutes=30)
        self.assertEqual(len(first), 1)
        self.assertTrue(first[0]["priority"])
        self.assertEqual(second, [])


if __name__ == "__main__":
    unittest.main()
