import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from skills import repo_workspace


class RepoWorkspaceTests(unittest.TestCase):
    def test_branch_name_is_restricted_and_prefixed(self):
        self.assertEqual(repo_workspace._safe_branch("feature"), "jarvis/feature")
        self.assertEqual(repo_workspace._safe_branch("jarvis/fix"), "jarvis/fix")
        for name in ("main", "master", "../bad", "bad..name", ""):
            with self.assertRaises(ValueError):
                repo_workspace._safe_branch(name)

    def test_write_file_stays_inside_repository(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            (repo / ".git").mkdir()
            with patch.object(repo_workspace, "repository_path", return_value=repo):
                self.assertTrue(repo_workspace.write_file("src/test.py", "print('ok')")["ok"])
                self.assertEqual((repo / "src/test.py").read_text(), "print('ok')")
                self.assertFalse(repo_workspace.write_file("../outside.py", "bad")["ok"])
                self.assertFalse(repo_workspace.write_file(".git/config", "bad")["ok"])

    def test_push_is_opt_in(self):
        with patch.dict(repo_workspace.os.environ, {"JARVIS_REPO_PUSH_ENABLED": "0"}, clear=False):
            result = repo_workspace.push_branch()
        self.assertFalse(result["ok"])
        self.assertIn("wyłączony", result["error"])

    def test_commit_is_blocked_on_main(self):
        with patch.object(repo_workspace, "_run", return_value={"ok": True, "output": "main"}):
            result = repo_workspace.commit_changes("nie zmieniaj main")
        self.assertFalse(result["ok"])
        self.assertIn("main/master", result["error"])

    def test_secret_scan_blocks_env(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            (repo / ".git").mkdir()
            (repo / ".env").write_text("GROQ_API_KEY=secret")
            with patch.object(repo_workspace, "repository_path", return_value=repo), patch.object(
                repo_workspace, "_run", side_effect=[
                    {"ok": True, "output": "jarvis/test"},
                    {"ok": True, "output": ""},
                ]
            ), patch.object(
                repo_workspace.subprocess, "run",
                return_value=type("Result", (), {"stdout": "?? .env\n"})(),
            ):
                result = repo_workspace.commit_changes("bez sekretu")
        self.assertFalse(result["ok"])
        self.assertIn("sekret", result["error"])

    def test_start_task_requires_clean_tree(self):
        with patch.object(repo_workspace, "_run", return_value={"ok": True, "output": " M main.py"}):
            result = repo_workspace.start_task("edukacja")
        self.assertFalse(result["ok"])
        self.assertIn("niezapisane", result["error"])

    def test_auto_merge_is_opt_in(self):
        with patch.dict(repo_workspace.os.environ, {"JARVIS_GITHUB_AUTO_MERGE": "0"}, clear=False):
            result = repo_workspace.create_and_merge_pr("test")
        self.assertFalse(result["ok"])
        self.assertIn("wyłączone", result["error"])


if __name__ == "__main__":
    unittest.main()
