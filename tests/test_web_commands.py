from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import Mock, patch

from skills import web_commands as commands
from test_tutoring import main_function


class WebCommandTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.database = Path(directory.name) / "commands.sqlite3"
        patcher = patch.object(commands, "DB_PATH", self.database)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_receipt_tracks_queued_processing_and_done(self):
        command_id = commands.submit_command("status sesji nauki")
        self.assertEqual(commands.command_result(command_id)["state"], "queued")
        self.assertEqual(commands.pop_pending_commands()[0]["id"], command_id)
        self.assertEqual(commands.command_result(command_id)["state"], "processing")
        commands.complete_command(command_id, "Odpowiedź")
        receipt = commands.command_result(command_id)
        self.assertEqual((receipt["state"], receipt["answer"]), ("done", "Odpowiedź"))
        commands.complete_command(command_id, "Duplikat")
        self.assertEqual(commands.command_result(command_id), receipt)
        self.assertIsNone(commands.command_result(9999))

    def test_old_database_is_kept_and_extended(self):
        with sqlite3.connect(self.database) as conn:
            conn.execute("CREATE TABLE web_commands (id INTEGER PRIMARY KEY AUTOINCREMENT, text TEXT NOT NULL, created_at TEXT NOT NULL, handled INTEGER NOT NULL DEFAULT 0)")
            conn.execute("INSERT INTO web_commands(text,created_at) VALUES ('stare polecenie','2026-01-01')")
        self.assertEqual(commands.pop_pending_commands()[0]["text"], "stare polecenie")
        commands.complete_command(1, "Gotowe")
        self.assertEqual(commands.command_result(1)["answer"], "Gotowe")

    def test_concurrent_workers_cannot_deliver_same_command_twice(self):
        ids = {commands.submit_command(str(i)) for i in range(6)}
        with ThreadPoolExecutor(max_workers=2) as pool:
            batches = list(pool.map(lambda _: commands.pop_pending_commands(), range(2)))
        delivered = [row["id"] for batch in batches for row in batch]
        self.assertEqual(set(delivered), ids)
        self.assertEqual(len(delivered), len(ids))

    def test_restart_reports_unknown_result_without_replaying_actions(self):
        interrupted = commands.submit_command("następne pytanie w sesji")
        finished = commands.submit_command("status sesji")
        commands.pop_pending_commands()
        commands.complete_command(finished, "Zapisany wynik")
        queued = commands.submit_command("pauza sesji nauki")
        commands.recover_interrupted_commands()
        self.assertIn("bez potwierdzenia", commands.command_result(interrupted)["answer"])
        self.assertEqual(commands.command_result(finished)["answer"], "Zapisany wynik")
        self.assertEqual(commands.command_result(queued)["state"], "queued")
        self.assertEqual([c["id"] for c in commands.pop_pending_commands()], [queued])

    def test_core_saves_response_before_audio_and_reports_exceptions(self):
        for fails in (False, True):
            command_id = commands.submit_command("status sesji")
            commands.pop_pending_commands()
            events = Mock()
            events.get_all.return_value = [{"type": "web_command", "command_id": command_id, "text": "status sesji"}]
            def speak(_):
                self.assertEqual(commands.command_result(command_id)["state"], "done")
            process = Mock(side_effect=ValueError("test")) if fails else Mock(return_value="Stan sesji")
            handler = main_function("handle_background_events", dict(
                background_events=events, set_gui_state=Mock(), process_command=process,
                complete_command=commands.complete_command, append_turn=Mock(), speak=speak,
            ))
            self.assertTrue(handler())
            result = commands.command_result(command_id)["answer"]
            self.assertIn("Nie udało się" if fails else "Stan sesji", result)
