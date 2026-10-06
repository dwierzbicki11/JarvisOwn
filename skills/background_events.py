import queue
import threading
import time

from skills.proactive import class_notification_due
from skills.reminders import has_due_reminders, pop_due_reminders
from skills.web_commands import has_pending_commands, pop_pending_commands


class BackgroundEvents:
    def __init__(self):
        self.queue = queue.Queue()
        self._stop = threading.Event()
        self._thread = None
        self._last_class_check = 0.0

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

            if now - self._last_class_check >= 300:
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

            self._stop.wait(1.0)
