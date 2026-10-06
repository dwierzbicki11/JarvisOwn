import unittest
from datetime import datetime, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

from skills.proactive import class_notification_due


TZ = ZoneInfo("Europe/Warsaw")


class ProactiveTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(
            2026,
            10,
            7,
            8,
            0,
            tzinfo=TZ,
        )

        self.event = {
            "summary": "Analiza matematyczna",
            "start": self.now + timedelta(
                minutes=65,
            ),
            "location": "A101",
        }

    @patch(
        "skills.proactive._claim_once",
        return_value=True,
    )
    @patch(
        "skills.proactive.commute_plan_for_first_class",
    )
    def test_leave_now_notice(
        self,
        plan,
        claim,
    ):
        departure = self.now + timedelta(
            minutes=10,
        )

        plan.return_value = {
            "event": self.event,
            "leave_home": self.now + timedelta(
                minutes=2,
            ),
            "journey": {
                "departure": departure,
                "arrival": self.now + timedelta(
                    minutes=50,
                ),
                "legs": [
                    {
                        "route": "297",
                        "departure": departure,
                    }
                ],
            },
        }

        answer = class_notification_due(
            now=self.now,
        )

        self.assertIsNotNone(answer)
        self.assertIn(
            "wychodzić",
            answer,
        )
        self.assertIn(
            "297",
            answer,
        )

    @patch(
        "skills.proactive._claim_once",
        return_value=True,
    )
    @patch(
        "skills.proactive.commute_plan_for_first_class",
    )
    def test_prepare_notice(
        self,
        plan,
        claim,
    ):
        plan.return_value = {
            "event": self.event,
            "leave_home": self.now + timedelta(
                minutes=30,
            ),
            "journey": {
                "departure": self.now + timedelta(
                    minutes=35,
                ),
                "legs": [],
            },
        }

        answer = class_notification_due(
            now=self.now,
        )

        self.assertIsNotNone(answer)
        self.assertIn(
            "powinieneś wyjść",
            answer,
        )

    @patch(
        "skills.proactive._claim_once",
        return_value=True,
    )
    @patch(
        "skills.proactive.commute_plan_for_first_class",
    )
    def test_class_notice_without_route(
        self,
        plan,
        claim,
    ):
        event = {
            "summary": "Techniki pomiarowe",
            "start": self.now + timedelta(
                minutes=60,
            ),
            "location": "C01",
        }

        plan.return_value = {
            "event": event,
            "leave_home": None,
            "journey": None,
        }

        answer = class_notification_due(
            now=self.now,
        )

        self.assertIsNotNone(answer)
        self.assertIn(
            "Techniki pomiarowe",
            answer,
        )
        self.assertIn(
            "C01",
            answer,
        )

    @patch(
        "skills.proactive._claim_once",
        return_value=False,
    )
    @patch(
        "skills.proactive.commute_plan_for_first_class",
    )
    def test_notice_only_once(
        self,
        plan,
        claim,
    ):
        plan.return_value = {
            "event": self.event,
            "leave_home": self.now + timedelta(
                minutes=2,
            ),
            "journey": {
                "departure": self.now + timedelta(
                    minutes=10,
                ),
                "legs": [
                    {
                        "route": "297",
                        "departure": self.now + timedelta(
                            minutes=10,
                        ),
                    }
                ],
            },
        }

        self.assertIsNone(
            class_notification_due(
                now=self.now,
            )
        )


if __name__ == "__main__":
    unittest.main()
