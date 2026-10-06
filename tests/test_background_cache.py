import threading
import time
import unittest

from skills.background_cache import BackgroundCache


class BackgroundCacheTests(unittest.TestCase):
    def test_first_get_returns_default_without_waiting(self):
        cache = BackgroundCache()
        release = threading.Event()

        def slow():
            release.wait(
                timeout=1,
            )
            return "ready"

        started = time.monotonic()
        value = cache.get(
            "slow",
            60,
            slow,
            default="loading",
        )
        elapsed = (
            time.monotonic()
            - started
        )

        self.assertEqual(
            value,
            "loading",
        )
        self.assertLess(
            elapsed,
            0.2,
        )

        release.set()

        for _ in range(50):
            if cache.get(
                "slow",
                60,
                slow,
            ) == "ready":
                break
            time.sleep(
                0.01
            )

        self.assertEqual(
            cache.get(
                "slow",
                60,
                slow,
            ),
            "ready",
        )

    def test_stale_value_is_returned_during_refresh(self):
        cache = BackgroundCache()
        cache._values["item"] = {
            "time": time.monotonic()
            - 100,
            "value": "old",
            "error": None,
        }

        release = threading.Event()

        def slow():
            release.wait(
                timeout=1,
            )
            return "new"

        value = cache.get(
            "item",
            1,
            slow,
        )

        self.assertEqual(
            value,
            "old",
        )

        release.set()


if __name__ == "__main__":
    unittest.main()
