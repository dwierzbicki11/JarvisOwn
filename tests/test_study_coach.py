import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from skills import study_coach


NOW = datetime(2026, 11, 16, 8, 0, tzinfo=timezone.utc)


class StudyCoachTests(unittest.TestCase):
    @patch(
        "skills.study_coach.study_summary",
        return_value=[
            {
                "subject": "matematyka",
                "interactions": 8,
                "last_at": (NOW - timedelta(days=1)).isoformat(),
            },
            {
                "subject": "programowanie",
                "interactions": 2,
                "last_at": (NOW - timedelta(days=6)).isoformat(),
            },
        ],
    )
    def test_neglected_subject_prefers_stale_area(
        self,
        _summary,
    ):
        rows = study_coach.neglected_subjects(
            now=NOW
        )

        self.assertEqual(
            rows[0]["subject"],
            "programowanie",
        )

    @patch(
        "skills.study_coach.list_cards",
        return_value=[
            {
                "id": 1,
                "question": "Co to jest pochodna?",
                "due_at": (NOW - timedelta(minutes=1)).isoformat(),
                "interval_days": 0,
                "reviews": 0,
            },
            {
                "id": 2,
                "question": "Co to jest całka?",
                "due_at": (NOW + timedelta(days=1)).isoformat(),
                "interval_days": 1,
                "reviews": 1,
            },
        ],
    )
    def test_due_flashcards_only_counts_due(
        self,
        _cards,
    ):
        data = study_coach.due_flashcard_summary(
            now=NOW
        )

        self.assertEqual(
            data["total"],
            2,
        )
        self.assertEqual(
            data["due"],
            1,
        )
        self.assertIn(
            "pochodna",
            data["examples"][0].lower(),
        )

    @patch(
        "skills.study_coach.pending_tasks",
        return_value=[
            {
                "id": 1,
                "text": "zrobić sprawozdanie z laboratorium",
                "due_at": NOW + timedelta(hours=8),
                "priority": True,
            },
            {
                "id": 2,
                "text": "kupić kabel USB",
                "due_at": NOW + timedelta(hours=2),
                "priority": True,
            },
        ],
    )
    def test_upcoming_study_tasks_filters_non_study(
        self,
        _tasks,
    ):
        rows = study_coach.upcoming_study_tasks(
            now=NOW
        )

        self.assertEqual(
            len(rows),
            1,
        )
        self.assertIn(
            "sprawozdanie",
            rows[0]["text"],
        )

    @patch(
        "skills.study_coach.build_snapshot",
        return_value={
            "flashcards": {
                "total": 8,
                "due": 3,
                "examples": [],
            },
            "study_tasks": [
                {
                    "text": "sprawozdanie",
                    "priority": True,
                }
            ],
            "neglected_subjects": [
                {
                    "subject": "programowanie",
                    "age_days": 5,
                }
            ],
        },
    )
    def test_build_plan_uses_local_priorities(
        self,
        _snapshot,
    ):
        plan = study_coach.build_study_plan(
            45,
            now=NOW,
        )

        self.assertEqual(
            sum(
                minutes
                for _, minutes
                in plan["blocks"]
            ),
            45,
        )
        labels = " ".join(
            label
            for label, _
            in plan["blocks"]
        )
        self.assertIn(
            "fiszki",
            labels,
        )
        self.assertIn(
            "sprawozdanie",
            labels,
        )

    @patch(
        "skills.study_coach.format_recommendation",
        return_value="Masz trzy fiszki do powtórki.",
    )
    def test_voice_recommendation_command(
        self,
        _recommendation,
    ):
        answer = (
            study_coach.process_study_coach_command(
                "Co mam dziś powtórzyć?"
            )
        )

        self.assertIn(
            "fiszki",
            answer,
        )

    @patch(
        "skills.study_coach.format_study_plan",
        return_value="Plan nauki na 60 minut.",
    )
    def test_voice_plan_command(
        self,
        formatter,
    ):
        answer = (
            study_coach.process_study_coach_command(
                "Zaplanuj mi 60 minut nauki"
            )
        )

        formatter.assert_called_once_with(
            60
        )
        self.assertIn(
            "60",
            answer,
        )


if __name__ == "__main__":
    unittest.main()
