import threading
import unittest
from unittest.mock import Mock, patch

import monitor


class ImmediateThread:
    def __init__(self, target, **kwargs):
        self.target = target

    def start(self):
        self.target()


class HeldThread(ImmediateThread):
    def start(self):
        pass


class MonitorTests(unittest.TestCase):
    def test_health_is_saved_before_intelligence_and_recovery(self):
        state = {"asterisk": "offline"}
        recovery = Mock()
        recovery.start_if_needed.side_effect = lambda value: events.append(
            ("recovery", dict(value))
        )
        events = []

        with patch.object(monitor, "load_previous_state", return_value={"old": True}), \
             patch.object(monitor, "build_state", return_value=state), \
             patch.object(monitor, "log_state_changes") as log_changes, \
             patch.object(monitor.automation, "observe_health", return_value={"mode": "active"}), \
             patch.object(monitor, "save_state", side_effect=lambda value: events.append(("save", dict(value)))), \
             patch.object(monitor, "build_intelligence", side_effect=lambda value: events.append(("intelligence", dict(value))) or {"summary": "ok"}):
            result = monitor.run_health_cycle(recovery)

        log_changes.assert_called_once_with({"old": True}, state)
        recovery.start_if_needed.assert_called_once_with(state)
        self.assertEqual(
            [item[0] for item in events],
            ["save", "recovery", "intelligence", "save"],
        )
        self.assertNotIn("intelligence", events[0][1])
        self.assertEqual(events[0][1]["automation"]["mode"], "active")
        self.assertEqual(result["intelligence_summary"], "ok")

    def test_fresh_health_survives_intelligence_failure(self):
        state = {"asterisk": "online"}
        recovery = Mock()
        saved = []
        with patch.object(monitor, "load_previous_state", return_value=None), \
             patch.object(monitor, "build_state", return_value=state), \
             patch.object(monitor, "log_state_changes"), \
             patch.object(monitor.automation, "observe_health", return_value={"mode": "active"}), \
             patch.object(monitor, "save_state", side_effect=lambda value: saved.append(dict(value))), \
             patch.object(monitor, "build_intelligence", side_effect=RuntimeError("broken")):
            with self.assertRaises(RuntimeError):
                monitor.run_health_cycle(recovery)

        self.assertEqual(saved, [{"asterisk": "online", "automation": {"mode": "active"}}])

    def test_recovery_is_claimed_before_thread_start_and_cannot_overlap(self):
        observed = []
        coordinator = None

        class InspectingHeldThread(HeldThread):
            def start(self):
                observed.append(coordinator._lock.locked())

        coordinator = monitor.RecoveryCoordinator(Mock(), InspectingHeldThread, lambda state: True)
        self.assertTrue(coordinator.start_if_needed({"asterisk": "offline"}))
        self.assertEqual(observed, [True])
        self.assertFalse(coordinator.start_if_needed({"asterisk": "offline"}))
        self.assertFalse(coordinator.start_if_needed({"asterisk": "online"}))

    def test_recovery_lock_is_released_after_worker_failure(self):
        worker = Mock(side_effect=RuntimeError("failed"))
        coordinator = monitor.RecoveryCoordinator(worker, ImmediateThread, lambda state: True)
        self.assertTrue(coordinator.start_if_needed({"asterisk": "offline"}))
        self.assertTrue(coordinator.start_if_needed({"asterisk": "offline"}))
        self.assertEqual(worker.call_count, 2)

    def test_periodic_loop_continues_after_failure(self):
        stop = threading.Event()
        operation = Mock()

        def second_call_stops():
            if operation.call_count == 1:
                raise RuntimeError("first")
            stop.set()

        operation.side_effect = second_call_stops
        monitor.run_periodic("test", operation, stop, interval=0)
        self.assertEqual(operation.call_count, 2)

    def test_slow_health_does_not_block_allstar_loop(self):
        stop = threading.Event()
        health_started = threading.Event()
        release_health = threading.Event()
        allstar_ran = threading.Event()

        def slow_health():
            health_started.set()
            release_health.wait(1)
            stop.set()

        def allstar():
            allstar_ran.set()
            release_health.set()

        health_thread = threading.Thread(target=monitor.run_periodic, args=("health", slow_health, stop, 0))
        allstar_thread = threading.Thread(target=monitor.run_periodic, args=("AllStar", allstar, stop, 0))
        health_thread.start()
        self.assertTrue(health_started.wait(1))
        allstar_thread.start()
        self.assertTrue(allstar_ran.wait(1))
        health_thread.join(1)
        allstar_thread.join(1)


if __name__ == "__main__":
    unittest.main()
