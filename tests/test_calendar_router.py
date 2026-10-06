import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

from skills.pk_calendar import (
    TIMEZONE,
    answer_calendar_question,
)


def event(
    summary,
    *,
    days=1,
    hour=9,
    minute=15,
    location="C01, budynek C",
):
    start = (
        datetime.now(TIMEZONE)
        + timedelta(
            days=days,
        )
    ).replace(
        hour=hour,
        minute=minute,
        second=0,
        microsecond=0,
    )

    return {
        "start": start,
        "end": start + timedelta(minutes=90),
        "summary": summary,
        "location": location,
    }


class CalendarRouterTests(unittest.TestCase):
    def setUp(self):
        self.events = [
            event(
                "Techniki pomiarowe dla informatyków — lab",
                days=1,
            ),
            event(
                "Techniki pomiarowe dla informatyków — wykład",
                days=2,
                hour=14,
                minute=30,
                location="A124, budynek A",
            ),
            event(
                "Analiza matematyczna — wykład",
                days=3,
                hour=8,
                minute=0,
                location="A101, budynek A",
            ),
        ]

    def answer(
        self,
        text,
        context_turns=None,
    ):
        with patch(
            "skills.pk_calendar._events_between",
            return_value=self.events,
        ):
            return answer_calendar_question(
                text,
                context_turns=context_turns,
            )

    def test_future_tense_laboratory_query_stays_local(self):
        answer = self.answer(
            "Kiedy będę miał techniki pomiarowe "
            "dla informatyków w laboratorium?"
        )

        self.assertIsNotNone(answer)
        self.assertIn(
            "Techniki pomiarowe dla informatyków",
            answer,
        )
        self.assertIn(
            "laboratorium",
            answer.lower(),
        )
        self.assertNotIn(
            "nie mam dostępu",
            answer.lower(),
        )

    def test_subject_query(self):
        answer = self.answer(
            "Kiedy mam przedmiot? Analiza matematyczna."
        )

        self.assertIsNotNone(answer)
        self.assertIn(
            "Analiza matematyczna",
            answer,
        )

    def test_activity_filter_selects_lab_not_lecture(self):
        answer = self.answer(
            "O której będę miał techniki pomiarowe "
            "dla informatyków w laboratorium?"
        )

        self.assertIn(
            "lab",
            answer.lower(),
        )
        self.assertNotIn(
            "A124",
            answer,
        )

    def test_transport_question_is_not_stolen_by_calendar(self):
        answer = self.answer(
            "Kiedy mam autobus?"
        )

        self.assertIsNone(answer)

    def test_calendar_followup_uses_history(self):
        context = [
            {
                "user": (
                    "Kiedy będę miał techniki pomiarowe "
                    "dla informatyków?"
                ),
                "assistant": (
                    "Najbliższe terminy zajęć podałem wcześniej."
                ),
            }
        ]

        answer = self.answer(
            "A w laboratorium?",
            context_turns=context,
        )

        self.assertIsNotNone(answer)
        self.assertIn(
            "Techniki pomiarowe dla informatyków",
            answer,
        )
        self.assertIn(
            "lab",
            answer.lower(),
        )


if __name__ == "__main__":
    unittest.main()
