"""Process presence is independent of the last conversation state change."""
import json
import threading
import time
from pathlib import Path


class CoreHeartbeat:
    def __init__(self, path, interval=5):
        self.path = Path(path)
        self.interval = interval
        self.stop_event = threading.Event()
        self.thread = None

    def pulse(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix('.tmp')
        temp.write_text(json.dumps({'updated': time.time()}), encoding='utf-8')
        temp.replace(self.path)

    def _run(self):
        while not self.stop_event.wait(self.interval):
            try:
                self.pulse()
            except OSError as exc:
                print(f'[HEARTBEAT ERROR] {exc}', flush=True)

    def start(self):
        self.pulse()
        self.thread = threading.Thread(target=self._run, daemon=True, name='core-heartbeat')
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=2)
        self.path.unlink(missing_ok=True)


def core_is_online(heartbeat_path, state_updated, now=None):
    now = time.time() if now is None else now
    try:
        data = json.loads(Path(heartbeat_path).read_text(encoding='utf-8'))
        updated = float(data['updated'])
        return 0 <= now - updated <= 20
    except (OSError, ValueError, TypeError, KeyError):
        # Compatibility with a core that has not yet been updated.
        try:
            return 0 <= now - float(state_updated) <= 45
        except (ValueError, TypeError):
            return False
