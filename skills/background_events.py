import os
import queue
import threading
import time

from skills.proactive import class_notification_due, headphone_battery_notification_due
from skills.reminders import has_due_reminders, pop_due_reminders
from skills.tasks import pop_due_task_notices
from skills.web_commands import has_pending_commands, pop_pending_commands

PROACTIVE_CHECK_SECONDS = max(
    30,
    int(
        os.getenv(
            "PROACTIVE_CHECK_SECONDS",
            "60",
        )
    ),
)

BATTERY_CHECK_SECONDS = max(
    60,
    int(
        os.getenv(
            "BATTERY_CHECK_SECONDS",
            "300",
        )
    ),
)

TASK_CHECK_SECONDS = max(
    30,
    int(
        os.getenv(
            "TASK_CHECK_SECONDS",
            "60",
        )
    ),
)

TASK_NOTICE_HORIZON_MINUTES = max(
    1,
    int(
        os.getenv(
            "TASK_NOTICE_HORIZON_MINUTES",
            "30",
        )
    ),
)


class BackgroundEvents:
    def __init__(self):
        self.queue = queue.Queue()
        self._stop = threading.Event()
        self._thread = None
        self._last_class_check = 0.0
        self._last_battery_check = 0.0
        self._last_task_check = 0.0

    def start(self):
        if self._thread and self._thread.is_alive():
            return

        self._thread = threading.Thread(
            target=self._worker,
            name="jarvis-background-events",
            daemon=True,
        )
        self._thread.start()

    def stop(self):
        self._stop.set()

    def pending(self):
        return not self.queue.empty()

    def get_all(self):
        events = []

        while True:
            try:
                events.append(self.queue.get_nowait())
            except queue.Empty:
                break

        return events

    def _worker(self):
        while not self._stop.is_set():
            try:
                if has_due_reminders():
                    for reminder in pop_due_reminders():
                        self.queue.put(
                            {
                                "type": "reminder",
                                "text": (
                                    "Przypomnienie: "
                                    + reminder["text"]
                                ),
                            }
                        )
            except Exception as exc:
                print(
                    f"[BACKGROUND REMINDER ERROR] {exc}",
                    flush=True,
                )

            try:
                if has_pending_commands():
                    for command in pop_pending_commands():
                        self.queue.put(
                            {
                                "type": "web_command",
                                "text": command["text"],
                            }
                        )
            except Exception as exc:
                print(
                    f"[BACKGROUND WEB ERROR] {exc}",
                    flush=True,
                )

            now = time.monotonic()

            if now - self._last_class_check >= PROACTIVE_CHECK_SECONDS:
                self._last_class_check = now

                try:
                    notice = class_notification_due()

                    if notice:
                        self.queue.put(
                            {
                                "type": "class",
                                "text": notice,
                            }
                        )

                except Exception as exc:
                    print(
                        f"[BACKGROUND CLASS ERROR] {exc}",
                        flush=True,
                    )

            if now - self._last_battery_check >= BATTERY_CHECK_SECONDS:
                self._last_battery_check = now

                try:
                    notice = headphone_battery_notification_due()

                    if notice:
                        self.queue.put(
                            {
                                "type": "headphones_battery",
                                "text": notice,
                            }
                        )

                except Exception as exc:
                    print(
                        f"[BACKGROUND BATTERY ERROR] {exc}",
                        flush=True,
                    )

            if now - self._last_task_check >= TASK_CHECK_SECONDS:
                self._last_task_check = now

                try:
                    for task in pop_due_task_notices(
                        horizon_minutes=TASK_NOTICE_HORIZON_MINUTES,
                    ):
                        minutes = task["minutes"]

                        if minutes < 0:
                            when_text = "Termin już minął."
                        elif minutes <= 1:
                            when_text = "Termin jest teraz."
                        else:
                            when_text = f"Termin za około {minutes} minut."

                        prefix = (
                            "Pilne zadanie. "
                            if task["priority"]
                            else "Zadanie. "
                        )

                        self.queue.put(
                            {
                                "type": "task",
                                "text": (
                                    prefix
                                    + task["text"]
                                    + ". "
                                    + when_text
                                ),
                            }
                        )

                except Exception as exc:
                    print(
                        f"[BACKGROUND TASK ERROR] {exc}",
                        flush=True,
                    )

            self._stop.wait(1.0)
