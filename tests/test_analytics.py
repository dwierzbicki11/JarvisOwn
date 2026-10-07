import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

from skills import analytics


TZ = ZoneInfo("Europe/Warsaw")


class AnalyticsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.focus_db = root / "jarvis.db"
        self.learning_db = root / "user_learning.sqlite3"
        self.study_db = root / "study_progress.db"
        self.now = datetime(
            2026,
            10,
            7,
            17,
            0,
            tzinfo=TZ,
        )

        self._create_learning_db()
        self._create_focus_db()
        self._create_study_db()

        self.patches = [
            patch.object(
                analytics,
                "FOCUS_DB_PATH",
                self.focus_db,
            ),
            patch.object(
                analytics,
                "LEARNING_DB_PATH",
                self.learning_db,
            ),
            patch.object(
                analytics,
                "STUDY_DB_PATH",
                self.study_db,
            ),
        ]

        for item in self.patches:
            item.start()

    def tearDown(self):
        for item in reversed(
            self.patches
        ):
            item.stop()

        self.tmp.cleanup()

    def _create_learning_db(self):
        with sqlite3.connect(
            self.learning_db
        ) as conn:
            conn.execute(
                """
                CREATE TABLE query_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    route TEXT NOT NULL,
                    subject TEXT,
                    keywords TEXT NOT NULL
                )
                """
            )

            rows = [
                (
                    self.now
                    - timedelta(days=1)
                ).isoformat(),
                (
                    self.now
                    - timedelta(days=2)
                ).isoformat(),
                (
                    self.now
                    - timedelta(days=10)
                ).isoformat(),
            ]

            conn.executemany(
                """
                INSERT INTO query_events(
                    created_at,
                    route,
                    subject,
                    keywords
                )
                VALUES (?, ?, ?, ?)
                """,
                [
                    (
                        rows[0],
                        "command",
                        "programowanie",
                        "python",
                    ),
                    (
                        rows[1],
                        "command",
                        "programowanie",
                        "numpy",
                    ),
                    (
                        rows[2],
                        "command",
                        "matematyka",
                        "macierz",
                    ),
                ],
            )

    def _create_focus_db(self):
        with sqlite3.connect(
            self.focus_db
        ) as conn:
            conn.execute(
                """
                CREATE TABLE focus_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    label TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    ends_at TEXT NOT NULL,
                    active INTEGER NOT NULL DEFAULT 1,
                    notified INTEGER NOT NULL DEFAULT 0,
                    stopped_at TEXT
                )
                """
            )

            recent_a = (
                self.now
                - timedelta(days=1)
            )
            recent_b = (
                self.now
                - timedelta(days=2)
            )
            old = (
                self.now
                - timedelta(days=10)
            )

            conn.executemany(
                """
                INSERT INTO focus_sessions(
                    label,
                    started_at,
                    ends_at,
                    active,
                    notified,
                    stopped_at
                )
                VALUES (?, ?, ?, 0, 0, ?)
                """,
                [
                    (
                        "programowanie",
                        recent_a.isoformat(),
                        (
                            recent_a
                            + timedelta(minutes=45)
                        ).isoformat(),
                        (
                            recent_a
                            + timedelta(minutes=45)
                        ).isoformat(),
                    ),
                    (
                        "matematyka",
                        recent_b.isoformat(),
                        (
                            recent_b
                            + timedelta(minutes=30)
                        ).isoformat(),
                        (
                            recent_b
                            + timedelta(minutes=30)
                        ).isoformat(),
                    ),
                    (
                        "angielski",
                        old.isoformat(),
                        (
                            old
                            + timedelta(minutes=60)
                        ).isoformat(),
                        (
                            old
                            + timedelta(minutes=60)
                        ).isoformat(),
                    ),
                ],
            )

    def _create_study_db(self):
        with sqlite3.connect(
            self.study_db
        ) as conn:
            conn.execute(
                """
                CREATE TABLE study_activity (
                    subject TEXT PRIMARY KEY,
                    interactions INTEGER NOT NULL,
                    last_at TEXT NOT NULL
                )
                """
            )
            conn.executemany(
                """
                INSERT INTO study_activity(
                    subject,
                    interactions,
                    last_at
                )
                VALUES (?, ?, ?)
                """,
                [
                    (
                        "programowanie",
                        8,
                        self.now.isoformat(),
                    ),
                    (
                        "matematyka",
                        5,
                        self.now.isoformat(),
                    ),
                ],
            )

    def test_build_weekly_report(self):
        report = analytics.build_report(
            days=7,
            now=self.now,
        )

        self.assertEqual(
            report["questions"],
            2,
        )
        self.assertEqual(
            report["focus_sessions"],
            2,
        )
        self.assertAlmostEqual(
            report["focus_minutes"],
            75.0,
        )
        self.assertAlmostEqual(
            report["average_focus_minutes"],
            37.5,
        )
        self.assertEqual(
            report[
                "lifetime_study_interactions"
            ],
            13,
        )
        self.assertEqual(
            report[
                "question_subjects"
            ][0]["value"],
            "programowanie",
        )

    def test_voice_command_uses_week(self):
        with patch.object(
            analytics,
            "format_report",
            return_value="raport",
        ) as mocked:
            result = (
                analytics
                .process_analytics_command(
                    "Jarvis, jak mi szła nauka w tym tygodniu?"
                )
            )

        self.assertEqual(
            result,
            "raport",
        )
        mocked.assert_called_once_with(
            days=7
        )

    def test_unrelated_command_is_ignored(self):
        self.assertIsNone(
            analytics
            .process_analytics_command(
                "Jaka jest pogoda?"
            )
        )


if __name__ == "__main__":
    unittest.main()
