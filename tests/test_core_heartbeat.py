import tempfile
import unittest
from pathlib import Path
from skills.core_heartbeat import CoreHeartbeat, core_is_online


class HeartbeatTests(unittest.TestCase):
    def test_idle_core_keeps_old_state_online(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'heartbeat.json'
            heartbeat = CoreHeartbeat(path)
            heartbeat.start()
            try:
                self.assertTrue(core_is_online(path, 1))
            finally:
                heartbeat.stop()
            self.assertFalse(core_is_online(path, 1))

    def test_crashed_core_expires(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'heartbeat.json'
            path.write_text('{"updated": 100}')
            self.assertTrue(core_is_online(path, 1, now=119))
            self.assertFalse(core_is_online(path, 121, now=121))

    def test_old_core_compatibility(self):
        self.assertTrue(core_is_online('/nonexistent/heartbeat.json', 100, now=120))
        self.assertFalse(core_is_online('/nonexistent/heartbeat.json', 100, now=146))
