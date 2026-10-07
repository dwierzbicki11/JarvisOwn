import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
from skills import flashcards as f


class FlashcardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        patcher = patch.object(f, 'DB_PATH', Path(self.temp.name) / 'data.db')
        patcher.start()
        self.addCleanup(patcher.stop)
        self.now = datetime(2026, 10, 7, tzinfo=timezone.utc)

    def test_duplicate_is_not_added(self):
        self.assertEqual(f.add_card('Ile to 2+2?', '4', self.now), f.add_card('Ile to 2+2?', '4', self.now))
        self.assertEqual(f.stats(self.now)['total'], 1)

    def test_answer_hidden_until_reveal_and_review_once(self):
        f.add_card('Pytanie', 'TAJNA ODPOWIEDZ', self.now)
        self.assertNotIn('TAJNA', f.next_question(self.now))
        self.assertIn('Najpierw', f.review(True, self.now))
        self.assertEqual(f.stats(self.now)['reviews'], 0)
        self.assertIn('TAJNA', f.reveal_answer())
        f.review(True, self.now)
        self.assertEqual(f.stats(self.now)['due'], 0)
        f.review(True, self.now)
        self.assertEqual(f.stats(self.now)['reviews'], 1)
        self.assertEqual(f.stats(self.now + timedelta(days=1))['due'], 1)

    def test_failed_review_returns_after_ten_minutes(self):
        f.add_card('A', 'B', self.now)
        first = f.next_question(self.now)
        self.assertEqual(f.next_question(self.now), first)
        f.reveal_answer()
        f.review(False, self.now)
        self.assertEqual(f.stats(self.now + timedelta(minutes=9))['due'], 0)
        self.assertEqual(f.stats(self.now + timedelta(minutes=10))['due'], 1)

    def test_commands_and_invalid_input(self):
        self.assertIsNone(f.process_flashcard_command('jaka pogoda'))
        self.assertIn('zapisana', f.process_flashcard_command('dodaj fiszkę stolica Polski odpowiedź Warszawa'))
        self.assertIn('Powiedz', f.process_flashcard_command('dodaj fiszkę'))
        with self.assertRaises(ValueError):
            f.add_card('', 'answer')
