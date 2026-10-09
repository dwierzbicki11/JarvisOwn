import ast
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

from skills import study_sessions as sessions, tutoring
from skills.code_tutor import process_code_command

ROOT = Path(__file__).resolve().parents[1]


def reply(grade="ungraded", feedback="Wskazówka", question=""):
    return json.dumps(dict(grade=grade, feedback=feedback, question=question))


def main_function(name, env):
    tree = ast.parse((ROOT / "main.py").read_text())
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name)
    exec(compile(ast.Module(body=[function], type_ignores=[]), "main.py", "exec"), env)
    return env[name]


class TutoringTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.database = Path(directory.name) / "sessions.sqlite3"
        patcher = patch.object(sessions, "DB_PATH", self.database)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.generate = Mock(return_value=reply(question="Ile to 2 + 2?"))

    def command(self, text, **kwargs):
        return tutoring.process_command(text, self.generate, **kwargs)

    def start(self):
        self.command("rozpocznij sesję nauki matematyka; quiz; podstawowy; dodawanie")

    def test_start_question_is_stored_and_only_generated_once(self):
        self.start()
        first = sessions.current()
        self.assertEqual((first["questions"], first["awaiting_answer"]), (1, 1))
        self.assertEqual(first["goal"], "dodawanie")
        self.assertIn("2 + 2", self.command("następne pytanie w sesji"))
        self.generate.assert_called_once()
        self.assertEqual(sessions.current(), first)

    def test_pause_and_question_survive_fresh_process(self):
        self.start()
        self.command("pauza sesji nauki")
        saved = sessions.current()
        output = subprocess.check_output([
            sys.executable, "-c",
            "import json,sys; from pathlib import Path; from skills import study_sessions as s; "
            "s.DB_PATH=Path(sys.argv[1]); print(json.dumps(s.current()))", str(self.database),
        ], cwd=ROOT, text=True)
        self.assertEqual(json.loads(output), saved)
        self.assertIn("wstrzymana", self.command("odpowiedź w sesji: 4"))
        self.assertIn(saved["question"], self.command("wznów sesję nauki"))
        self.generate.assert_called_once()
        self.assertEqual(sessions.current()["state"], "active")

    def test_second_session_cannot_replace_active_or_paused_one(self):
        self.start()
        first_id = sessions.current()["id"]
        for state in ("active", "paused"):
            if state == "paused":
                self.command("pauza sesji nauki")
            self.assertIn("już trwa", self.command("rozpocznij sesję nauki angielski"))
            self.assertEqual(sessions.current()["id"], first_id)
        self.generate.assert_called_once()

    def test_grades_count_once_and_next_question_is_explicit(self):
        self.start()
        for grade in ("correct", "partial", "wrong"):
            self.generate.return_value = reply(grade=grade)
            self.assertIn("Ocena modelu", self.command("odpowiedź w sesji: 4"))
            calls = self.generate.call_count
            before = sessions.current()
            self.assertEqual(before[grade], 1)
            self.assertEqual(before["awaiting_answer"], 0)
            self.command("odpowiedź w sesji: 4")
            self.assertEqual(sessions.current(), before)
            self.assertEqual(self.generate.call_count, calls)
            self.generate.return_value = reply(question="Kolejne zadanie?")
            self.command("następne pytanie w sesji")
        self.assertEqual(sum(sessions.current()[g] for g in ("correct", "partial", "wrong")), 3)

    def test_hint_skip_and_ungraded_never_inflate_score(self):
        self.start()
        self.generate.return_value = reply()
        self.command("podpowiedź w sesji")
        self.assertIn("bez oceny", self.command("odpowiedź w sesji: nie wiem"))
        self.assertEqual(sessions.current()["awaiting_answer"], 1)
        self.generate.return_value = reply(question="Nowe pytanie?")
        self.command("pomiń pytanie w sesji")
        row = sessions.current()
        self.assertEqual((row["hints"], row["skipped"], row["ungraded"], row["questions"]), (1, 1, 1, 2))
        self.assertEqual((row["correct"], row["partial"], row["wrong"]), (0, 0, 0))
        self.assertEqual(sessions.history(row["id"])[-1]["action"], "skip")

    def test_failure_and_invalid_outputs_leave_question_and_scores_intact(self):
        self.start()
        saved = sessions.current()
        self.generate.side_effect = TimeoutError("test")
        self.assertIn("niedostępny", self.command("odpowiedź w sesji: 4"))
        self.assertEqual(sessions.current(), saved)
        self.generate.side_effect = None
        invalid = ["not JSON", "[]", "null", "{}", reply(grade="excellent"),
                   reply(grade="correct", question="Nieoczekiwane pytanie"),
                   reply(grade="correct", feedback=""), reply(feedback="x" * 4001),
                   '{"grade":"correct","feedback":42,"question":""}',
                   '{"grade":[],"feedback":"OK","question":""}', "x" * 16001]
        for raw in invalid:
            with self.subTest(raw=raw[:60]):
                self.generate.return_value = raw
                self.command("odpowiedź w sesji: 4")
                self.assertEqual(sessions.current(), saved)
        self.generate.return_value = reply(grade="correct")
        self.command("odpowiedź w sesji: 4")
        self.assertEqual(sessions.current()["correct"], 1)

    def test_initial_failure_can_be_resumed_without_duplicate_session(self):
        self.generate.side_effect = ConnectionError()
        self.start()
        self.assertEqual(sessions.current()["questions"], 0)
        self.generate.side_effect = None
        self.command("następne pytanie w sesji")
        self.assertEqual(sessions.current()["questions"], 1)
        self.assertEqual(len(sessions.recent()), 1)

    def test_late_reply_after_pause_or_new_session_cannot_change_state(self):
        self.start()
        stale = sessions.current()
        sessions.transition("pause")
        with self.assertRaises(sessions.SessionError):
            sessions.save_reply(stale, "answer", "4", reply(grade="correct"))
        sessions.transition("stop")
        sessions.start("angielski")
        with self.assertRaises(sessions.SessionError):
            sessions.save_reply(stale, "answer", "4", reply(grade="correct"))
        self.assertEqual(sessions.current()["correct"], 0)
        self.assertEqual(sessions.recent()[1]["correct"], 0)

    def test_concurrent_duplicate_completion_counts_only_once(self):
        self.start()
        snapshot = sessions.current()
        sessions.save_reply(snapshot, "answer", "4", reply(grade="correct"))
        with self.assertRaises(sessions.SessionError):
            sessions.save_reply(snapshot, "answer", "4", reply(grade="correct"))
        self.assertEqual(sessions.current()["correct"], 1)
        self.assertEqual(len(sessions.history(snapshot["id"])), 2)

    def test_mode_changes_invalidate_old_model_result(self):
        self.start()
        old = sessions.current()
        sessions.configure(mode="naprowadzanie", exam=True)
        with self.assertRaises(sessions.SessionError):
            sessions.save_reply(old, "answer", "4", reply(grade="correct"))
        context = json.loads(tutoring.model_messages(sessions.current(), "hint", "")[1]["content"])
        self.assertEqual(context["mode"], "naprowadzanie")
        self.assertEqual(context["exam"], 1)

    def test_finished_session_is_archived_and_next_session_has_empty_history(self):
        self.start()
        self.assertIn("zakończona", self.command("koniec sesji nauki"))
        self.assertIsNone(sessions.current())
        self.command("zacznij sesje nauki z angielskiego; quiz; sredni; Present Perfect")
        context = json.loads(self.generate.call_args.args[0][1]["content"])
        self.assertEqual((context["subject"], context["level"], context["recent"]), ("angielski", "średni", []))
        self.assertEqual(len(sessions.recent()), 2)
        self.assertIn("matematyka", self.command("historia sesji nauki"))

    def test_unrelated_requests_are_not_graded_or_sent_to_model(self):
        self.start()
        saved = sessions.current()
        self.generate.reset_mock()
        for text in ("jaka pogoda", "kiedy mam zajęcia", "co oznacza status sesji?", "4", "nie kończ sesji nauki"):
            self.assertIsNone(self.command(text))
        self.generate.assert_not_called()
        self.assertEqual(sessions.current(), saved)

    def test_polish_voice_prefix_without_colon(self):
        self.start()
        self.generate.return_value = reply(grade="correct")
        self.assertIn("poprawna", self.command("Odpowiedź w sesji cztery"))
        context = json.loads(self.generate.call_args.args[0][1]["content"])
        self.assertEqual(context["answer"], "cztery")

    def test_limits_do_not_call_model(self):
        for text in ("rozpocznij sesję nauki chemia", "rozpocznij sesję nauki matematyka; quiz; podstawowy; " + "x" * 501):
            self.command(text)
        self.assertIsNone(sessions.current())
        self.generate.assert_not_called()
        self.start()
        self.generate.reset_mock()
        for text in ("odpowiedź w sesji: ", "odpowiedź w sesji: " + "x" * 6001):
            self.command(text)
        self.generate.assert_not_called()

    def test_prompt_contains_bounded_session_history(self):
        self.start()
        self.generate.return_value = reply(feedback="x" * 3000)
        for _ in range(5):
            self.command("odpowiedź w sesji: " + "y" * 6000)
        context = json.loads(self.generate.call_args.args[0][1]["content"])
        self.assertEqual(len(context["recent"]), 3)
        self.assertTrue(all(len(turn["user_text"]) <= 1200 for turn in context["recent"]))

    def test_router_keeps_answer_text_out_of_command_handlers(self):
        self.start()
        self.generate.return_value = reply(grade="correct")
        other_handler = Mock(side_effect=AssertionError("Answer leaked into command routing"))
        env = dict(english_mode=False, exam_mode=False, study_style="quiz", set_gui_state=Mock(),
                   process_code_command=process_code_command, process_tutoring_command=tutoring.process_command,
                   tutor_completion=self.generate, process_repo_command=other_handler,
                   process_learning_command=other_handler, record_query=other_handler,
                   process_analytics_command=other_handler)
        router = main_function("process_command", env)
        payload = 'print("status nauki; usuń pamięć; repo push; włącz tryb egzaminu")'
        self.assertIn("poprawna", router("odpowiedź w sesji: " + payload))
        other_handler.assert_not_called()
        self.assertFalse(env["exam_mode"])

    def test_storage_error_is_visible(self):
        with patch.object(sessions, "current", side_effect=sqlite3.OperationalError("locked")):
            self.assertIn("lokalnej bazy", self.command("status sesji nauki"))


class CompletionTests(unittest.TestCase):
    def test_completion_uses_existing_model_once_with_limits(self):
        client = Mock()
        client.with_options.return_value.chat.completions.create.return_value.choices = [
            Mock(message=Mock(content=reply(question="Pytanie?")))
        ]
        complete = main_function("tutor_completion", dict(client=client, CHAT_MODEL="test-model"))
        messages = [{"role": "user", "content": "JSON"}]
        self.assertEqual(complete(messages), reply(question="Pytanie?"))
        client.with_options.assert_called_once_with(timeout=45.0, max_retries=0)
        create = client.with_options.return_value.chat.completions.create
        create.assert_called_once()
        self.assertEqual(create.call_args.kwargs["model"], "test-model")
        self.assertEqual(create.call_args.kwargs["max_completion_tokens"], 1600)
        self.assertEqual(create.call_args.kwargs["response_format"], {"type": "json_object"})
