import threading
import time


class BackgroundCache:
    """
    Thread-safe stale-while-revalidate cache.

    get() nigdy nie czeka na wolny loader:
    - świeża wartość: zwracana od razu,
    - stara wartość: zwracana od razu + odświeżenie w tle,
    - brak wartości: zwraca default + uruchamia loader w tle.
    """

    def __init__(self):
        self._values = {}
        self._running = set()
        self._lock = threading.Lock()

    def _refresh(
        self,
        name,
        loader,
    ):
        try:
            value = loader()

            with self._lock:
                self._values[name] = {
                    "time": time.monotonic(),
                    "value": value,
                    "error": None,
                }

        except Exception as exc:
            with self._lock:
                old = self._values.get(name)

                if old is None:
                    self._values[name] = {
                        "time": 0.0,
                        "value": None,
                        "error": str(exc),
                    }
                else:
                    old["error"] = str(exc)

        finally:
            with self._lock:
                self._running.discard(
                    name
                )

    def get(
        self,
        name,
        ttl,
        loader,
        *,
        default=None,
    ):
        now = time.monotonic()

        with self._lock:
            cached = self._values.get(
                name
            )

            if (
                cached is not None
                and cached["time"] > 0
                and now - cached["time"] < ttl
            ):
                return cached[
                    "value"
                ]

            if name not in self._running:
                self._running.add(
                    name
                )

                thread = threading.Thread(
                    target=self._refresh,
                    args=(
                        name,
                        loader,
                    ),
                    name=(
                        "jarvis-gui-cache-"
                        + name
                    ),
                    daemon=True,
                )
                thread.start()

            if cached is not None:
                return cached[
                    "value"
                ]

            return default

    def state(
        self,
    ):
        with self._lock:
            return {
                "running": sorted(
                    self._running
                ),
                "ready": sorted(
                    name
                    for name, item in self._values.items()
                    if item.get(
                        "time",
                        0,
                    ) > 0
                ),
                "errors": {
                    name: item["error"]
                    for name, item in self._values.items()
                    if item.get(
                        "error"
                    )
                },
            }
