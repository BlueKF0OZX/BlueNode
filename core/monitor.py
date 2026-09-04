#!/usr/bin/env python3

"""Run BlueNode's independent monitoring and recovery workloads."""

import threading
import time

from allstar_status import check_changes
from health import build_state, load_previous_state, log_state_changes, save_state
from intelligence import build_intelligence
from recovery import recover_asterisk
import automation
import connectivity
import node_behavior


POLL_INTERVAL_SECONDS = 2


class RecoveryCoordinator:
    """Allow at most one background recovery attempt at a time."""

    def __init__(self, worker=recover_asterisk, thread_factory=threading.Thread,
                 recovery_policy=automation.recovery_allowed):
        self._worker = worker
        self._thread_factory = thread_factory
        self._recovery_policy = recovery_policy
        self._lock = threading.Lock()

    def start_if_needed(self, state):
        if state.get("asterisk") != "offline":
            return False
        if not self._recovery_policy(state):
            return False

        # Claim recovery before creating the thread. A second health pass can
        # never observe an unlocked interval between start() and worker entry.
        if not self._lock.acquire(blocking=False):
            return False

        try:
            thread = self._thread_factory(
                target=self._run,
                name="nodesmart-recovery",
                daemon=True,
            )
            thread.start()
        except Exception:
            self._lock.release()
            raise

        return True

    def _run(self):
        try:
            self._worker()
        except Exception as exc:
            print(f"BlueNode recovery worker error: {exc}", flush=True)
        finally:
            self._lock.release()


def run_health_cycle(recovery):
    """Collect, persist, enrich, and repersist one health observation."""
    previous_state = load_previous_state()
    state = build_state()
    log_state_changes(previous_state, state)

    # Preserve the observation even if Intelligence fails or takes extra time.
    state["automation"] = automation.observe_health(state)
    state["node_behavior"] = node_behavior.observe(
        state.get("radio_activity"), state["automation"], state.get("connectivity")
    )
    save_state(state)
    recovery.start_if_needed(state)

    state["intelligence"] = build_intelligence(state)
    state["intelligence_summary"] = state["intelligence"]["summary"]
    save_state(state)
    return state


def run_periodic(name, operation, stop_event, interval=POLL_INTERVAL_SECONDS):
    """Run a workload repeatedly without allowing one failure to end its loop."""
    while not stop_event.is_set():
        started = time.monotonic()
        try:
            operation()
        except Exception as exc:
            print(f"BlueNode {name} loop error: {exc}", flush=True)

        remaining = max(0, interval - (time.monotonic() - started))
        stop_event.wait(remaining)


def main():
    stop_event = threading.Event()
    recovery = RecoveryCoordinator()
    try:
        connectivity.update()
    except Exception as exc:
        print(f"BlueNode connectivity startup error: {exc}", flush=True)
    threads = [
        threading.Thread(
            target=run_periodic,
            args=("health", lambda: run_health_cycle(recovery), stop_event),
            name="nodesmart-health",
        ),
        threading.Thread(
            target=run_periodic,
            args=("AllStar", check_changes, stop_event),
            name="nodesmart-allstar",
        ),
        threading.Thread(
            target=run_periodic,
            args=("connectivity", connectivity.update, stop_event,
                  connectivity.INTERVAL_SECONDS),
            name="nodesmart-connectivity",
        ),
    ]

    for thread in threads:
        thread.start()

    try:
        while all(thread.is_alive() for thread in threads):
            stop_event.wait(1)
    except KeyboardInterrupt:
        pass
    finally:
        stop_event.set()
        for thread in threads:
            thread.join()


if __name__ == "__main__":
    main()
