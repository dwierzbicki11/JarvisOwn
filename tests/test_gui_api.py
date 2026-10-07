import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
import jarvis_gui as gui
from skills import flashcards


class GuiApiTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        directory = self.stack.enter_context(tempfile.TemporaryDirectory())
        self.stack.enter_context(patch.object(flashcards, 'DB_PATH', Path(directory) / 'cards.db'))
        # Do not start background hardware/network jobs in HTTP contract tests.
        self.client = TestClient(gui.app)
        self.addCleanup(self.client.close)

    def test_status_uses_existing_cache_without_network(self):
        with patch.object(gui.status_cache, 'get', side_effect=lambda *a, **kw: kw.get('default')) as get, patch.object(gui, 'recent_turns', return_value=[]), patch.object(gui, 'system_data', return_value={}), patch.object(gui, 'jarvis_state', return_value={'state': 'standby'}):
            response = self.client.get('/api/status')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['jarvis']['state'], 'standby')
        self.assertGreater(get.call_count, 5)

    def test_create_edit_delete_and_missing(self):
        created = self.client.post('/api/flashcards', json={'question': 'Two plus two?', 'answer': '4'})
        self.assertEqual(created.status_code, 200)
        card_id = created.json()['id']
        self.assertEqual(len(self.client.get('/api/flashcards').json()['cards']), 1)
        edited = self.client.put(f'/api/flashcards/{card_id}', json={'question': 'Three plus two?', 'answer': '5'})
        self.assertEqual(edited.status_code, 200)
        self.assertEqual(self.client.get('/api/flashcards').json()['cards'][0]['answer'], '5')
        self.assertEqual(self.client.delete(f'/api/flashcards/{card_id}').status_code, 200)
        self.assertEqual(self.client.delete(f'/api/flashcards/{card_id}').status_code, 404)
        self.assertEqual(self.client.get('/api/flashcards').json()['cards'], [])

    def test_validation_and_duplicate_edit(self):
        self.assertEqual(self.client.post('/api/flashcards', json={'question': '  ', 'answer': 'A'}).status_code, 400)
        self.assertEqual(self.client.post('/api/flashcards', json={'question': 'Q', 'answer': 'x' * 4001}).status_code, 422)
        first = flashcards.add_card('Q1', 'A1')
        flashcards.add_card('Q2', 'A2')
        self.assertEqual(self.client.put(f'/api/flashcards/{first}', json={'question': 'Q2', 'answer': 'A2'}).status_code, 400)
        self.assertEqual(len(flashcards.list_cards()), 2)

    def test_edit_clears_reveal_and_delete_clears_session(self):
        card = flashcards.add_card('Q', 'old')
        flashcards.next_question()
        flashcards.reveal_answer()
        flashcards.edit_card(card, 'Q', 'new')
        self.assertIn('Najpierw', flashcards.review(True))
        self.assertIn('new', flashcards.reveal_answer())
        flashcards.delete_card(card)
        self.assertIn('Nie ma aktywnej', flashcards.review(True))

    def test_page_available(self):
        with patch.object(gui, 'HTML_FILE', Path(gui.__file__).parent / 'gui' / 'index.html'):
            response = self.client.get('/flashcards')
        self.assertEqual(response.status_code, 200)
        self.assertIn('Twoje fiszki', response.text)
