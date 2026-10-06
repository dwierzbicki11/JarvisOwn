import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

from skills import scheduled_briefing


TZ = ZoneInfo("Europe/Warsaw")


class ScheduledBriefingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state_path = (
            Path(self.tmp.name)
            / "briefings.json"
        )

        self.state_patch = patch.object(
            scheduled_briefing,
            "STATE_FILE",
            self.state_path,
        )
        self.state_patch.start()

    def tearDown(self):
        self.state_patch.stop()
        self.tmp.cleanup()

    @patch.object(
        scheduled_briefing,
        "BRIEFING_ENABLED",
        True,
    )
    @patch.object(
        scheduled_briefing,
        "BRIEFING_MORNING_TIME",
        "07:00",
    )
    @patch.object(
        scheduled_briefing,
        "BRIEFING_EVENING_TIME",
        "21:00",
    )
    def test_morning_briefing_only_once(self):
        now = datetime(
            2026,
            10,
            7,
            7,
            5,
            tzinfo=TZ,
        )

        self.assertEqual(
            scheduled_briefing.briefing_due(
                now=now,
            ),
            "today",
        )

        self.assertIsNone(
            scheduled_briefing.briefing_due(
                now=now,
            )
        )

    @patch.object(
        scheduled_briefing,
        "BRIEFING_ENABLED",
        True,
    )
    @patch.object(
        scheduled_briefing,
        "BRIEFING_MORNING_TIME",
        "07:00",
    )
    @patch.object(
        scheduled_briefing,
        "BRIEFING_EVENING_TIME",
        "21:00",
    )
    def test_evening_briefing(self):
        now = datetime(
            2026,
            10,
            7,
            21,
            10,
            tzinfo=TZ,
        )

        self.assertEqual(
            scheduled_briefing.briefing_due(
                now=now,
            ),
            "tomorrow",
        )

    @patch.object(
        scheduled_briefing,
        "BRIEFING_ENABLED",
        True,
    )
    @patch.object(
        scheduled_briefing,
        "BRIEFING_CATCHUP_MINUTES",
        60,
    )
    @patch.object(
        scheduled_briefing,
        "BRIEFING_MORNING_TIME",
        "07:00",
    )
    @patch.object(
        scheduled_briefing,
        "BRIEFING_EVENING_TIME",
        "21:00",
    )
    def test_no_late_morning_briefing(self):
        now = datetime(
            2026,
            10,
            7,
            12,
            0,
            tzinfo=TZ,
        )

        self.assertIsNone(
            scheduled_briefing.briefing_due(
                now=now,
            )
        )


if __name__ == "__main__":
    unittest.main()
