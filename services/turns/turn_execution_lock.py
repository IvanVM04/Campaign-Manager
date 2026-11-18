from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager


class TurnExecutionLock:
    """Protect short campaign snapshot, commit and shared-cache critical sections.

    Provider inference and narration must never run while this lock is held.
    SQLite revisions and durable planning leases fence speculative work.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()

    @contextmanager
    def acquire(self) -> Iterator[None]:
        with self._lock:
            yield