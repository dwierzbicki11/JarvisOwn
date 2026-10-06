import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from skills import health_alerts


class HealthAlertTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state_path = (
            Path(self.tmp.name)
            / "health.json"
        )
        self.state_patch = patch.object(
            health_alerts,
            "STATE_FILE",
            self.state_path,
        )
        self.state_patch.start()

    def tearDown(self):
        self.state_patch.stop()
        self.tmp.cleanup()

    @patch.object(
        health_alerts,
        "HEALTH_ALERTS_ENABLED",
        True,
    )
    @patch(
        "skills.health_alerts._conditions",
        return_value={
            "disk": (
                "Uwaga. Dysk systemowy jest zajęty "
                "w 95 procentach."
            )
        },
    )
    def test_same_alert_only_once(
        self,
        conditions,
    ):
        first = health_alerts.health_alert_due()
        second = health_alerts.health_alert_due()

        self.assertIsNotNone(first)
        self.assertIsNone(second)

    @patch.object(
        health_alerts,
        "HEALTH_ALERTS_ENABLED",
        True,
    )
    def test_alert_resets_after_recovery(self):
        with patch(
            "skills.health_alerts._conditions",
            return_value={
                "ram": (
                    "Uwaga. Wykorzystanie pamięci RAM "
                    "wynosi 97 procent."
                )
            },
        ):
            self.assertIsNotNone(
                health_alerts.health_alert_due()
            )

        with patch(
            "skills.health_alerts._conditions",
            return_value={},
        ):
            self.assertIsNone(
                health_alerts.health_alert_due()
            )

        with patch(
            "skills.health_alerts._conditions",
            return_value={
                "ram": (
                    "Uwaga. Wykorzystanie pamięci RAM "
                    "wynosi 97 procent."
                )
            },
        ):
            self.assertIsNotNone(
                health_alerts.health_alert_due()
            )


if __name__ == "__main__":
    unittest.main()
