import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import automation


class AutomationTests(unittest.TestCase):
    def setUp(self):
        enabled = patch.object(automation, "RECOVERY_ENABLED", True)
        enabled.start()
        self.addCleanup(enabled.stop)
        self.directory = tempfile.TemporaryDirectory()
        self.state_file = Path(self.directory.name) / "automation.json"
        self.state_patch = patch.object(automation, "STATE_FILE", self.state_file)
        self.state_patch.start()
        self.events = patch.object(automation, "emit")
        self.emit = self.events.start()

    def tearDown(self):
        self.events.stop()
        self.state_patch.stop()
        self.directory.cleanup()

    def test_isolated_recovery_verifies_and_resumes(self):
        self.assertTrue(automation.recovery_allowed({"asterisk": "offline"}, 1000))
        self.assertEqual(automation.begin_recovery(1000), 1)
        recovered = automation.finish_recovery(True, "verified", 1010)
        self.assertEqual(recovered["mode"], "recovered")
        active = automation.observe_health({"asterisk": "online"},
                                            1010 + automation.HEALTHY_RESET_SECONDS)
        self.assertEqual(active["mode"], "active")
        self.assertEqual(active["recent_recovery_attempts"], [])

    def test_repeated_outages_escalate_and_back_off(self):
        for stamp in (1000, 1010, 1020):
            state = automation.load_state()
            state["cooldown_until"] = 0
            automation.save_state(state)
            self.assertIsNotNone(automation.begin_recovery(stamp))
            automation.finish_recovery(True, "verified", stamp + 1)
        state = automation.load_state()
        self.assertEqual(state["mode"], "attention")
        self.assertGreater(state["backoff_until"], 1020)
        self.assertFalse(automation.recovery_allowed({"asterisk": "offline"}, 1030))

    def test_failed_verification_escalates(self):
        automation.begin_recovery(1000)
        first = automation.finish_recovery(False, "unhealthy", 1001)
        self.assertEqual(first["mode"], "active")
        state = automation.load_state(); state["cooldown_until"] = 0
        automation.save_state(state)
        automation.begin_recovery(1010)
        second = automation.finish_recovery(False, "still unhealthy", 1011)
        self.assertEqual(second["mode"], "attention")
        self.assertEqual(second["last_verification"]["passed"], False)

    def test_maintenance_suppresses_recovery_and_monitoring_continues(self):
        maintenance = automation.set_maintenance(True, 1000)
        self.assertTrue(maintenance["maintenance_mode"])
        observed = automation.observe_health({"asterisk": "offline"}, 1001)
        self.assertIsNotNone(observed["last_automation_check"])
        self.assertFalse(automation.recovery_allowed({"asterisk": "offline"}, 1001))
        resumed = automation.set_maintenance(False, 1002)
        self.assertTrue(resumed["automation_armed"])
        self.assertTrue(automation.recovery_allowed({"asterisk": "offline"}, 1002))

    def test_persistence_and_malformed_state(self):
        automation.set_maintenance(True, 1000)
        self.assertTrue(automation.load_state()["maintenance_mode"])
        self.state_file.write_text("{broken", encoding="utf-8")
        state = automation.load_state()
        self.assertEqual(state, automation.default_state())
        automation.save_state(state)
        self.assertEqual(json.loads(self.state_file.read_text())["version"], 1)

    def test_connectivity_failure_never_requests_asterisk_recovery(self):
        for domain in ("local_network", "gateway", "dns", "external_internet",
                       "allstar_services", "allstar_registration", "asterisk",
                       "iax", "remote_link"):
            with self.subTest(domain=domain):
                health = {"asterisk": "online", "connectivity": {
                    "status": "offline", "failure_domain": domain}}
                observed = automation.observe_health(health, 1000)
                self.assertEqual(observed["connectivity_failure_domain"], domain)
                self.assertEqual(observed["connectivity_action"], "monitoring_only")
                self.assertFalse(automation.recovery_allowed(health, 1000))


if __name__ == "__main__":
    unittest.main()
