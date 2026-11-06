import threading
import time
from concurrent.futures import ThreadPoolExecutor

from services.turns import TurnExecutionLock


def test_turn_execution_lock_serializes_concurrent_execution():
    lock = TurnExecutionLock()

    active_turns = 0
    max_active_turns = 0

    state_lock = threading.Lock()
    start_barrier = threading.Barrier(2)

    def execute_turn():
        nonlocal active_turns
        nonlocal max_active_turns

        start_barrier.wait()

        with lock.acquire():
            with state_lock:
                active_turns += 1
                max_active_turns = max(
                    max_active_turns,
                    active_turns,
                )

            time.sleep(0.05)

            with state_lock:
                active_turns -= 1

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(execute_turn),
            executor.submit(execute_turn),
        ]

        for future in futures:
            future.result()

    assert max_active_turns == 1
