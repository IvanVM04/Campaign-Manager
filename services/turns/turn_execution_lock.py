from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager


class TurnExecutionLock:
    """
    Serializa la ejecución de turnos que pueden modificar
    el estado compartido de la campaña.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()

    @contextmanager
    def acquire(self) -> Iterator[None]:
        with self._lock:
            yield