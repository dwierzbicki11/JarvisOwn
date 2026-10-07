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


if __name__ == "__main__":
    unittest.main()
