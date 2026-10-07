import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from skills import memory_store


class MemorySearchTests(unittest.TestCase):
    def test_search_is_local_and_accent_tolerant(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(memory_store, "DB_PATH", Path(directory) / "memory.db"):
                memory_store.remember("Studiuję informatykę stosowaną na Politechnice Krakowskiej.")
                memory_store.remember("Gram na czterostrunowej gitarze basowej.")
                results = memory_store.search_memories("politechnika krakowska")
                self.assertEqual(len(results), 1)
                self.assertIn("informatykę", results[0]["text"])

    def test_empty_query_does_not_return_everything(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(memory_store, "DB_PATH", Path(directory) / "memory.db"):
                memory_store.remember("Ważna informacja")
                self.assertEqual(memory_store.search_memories(""), [])


if __name__ == "__main__":
    unittest.main()

