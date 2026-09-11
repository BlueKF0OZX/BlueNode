import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import automation


def stopped(now):
    return {"asterisk": "offline", "asterisk_evidence": {"service": {
        "status": "offline", "observed_at": now, "load_state": "loaded",
        "active_state": "inactive", "sub_state": "dead", "main_pid": 0}}}


class AutomationTests(unittest.TestCase):
    def setUp(self):
        enabled = patch.object(automation, "RECOVERY_ENABLED", True)
        enabled.start()
        self.addCleanup(enabled.stop)
        self.directory = tempfile.TemporaryDirectory()
        self.state_file = Path(self.directory.name) / "automation.json"
        self.state_patch = patch.object(automation, "STATE_FILE", self.state_file)
        self.state_patch.start()
        automation.save_state(automation.default_state())
        self.events = patch.object(automation, "emit")
        self.emit = self.events.start()

    def tearDown(self):
        self.events.stop()
        self.state_patch.stop()
        self.directory.cleanup()

    def assert_inhibited(self):
        original = self.state_file.read_bytes() if self.state_file.exists() else None
        self.assertFalse(automation.recovery_allowed(stopped(1000), 1000))
        self.assertIsNone(automation.begin_recovery(1000))
        for result in (automation.observe_health({'asterisk': 'online'}, 2000),
                       automation.set_maintenance(False, 2001),
                       automation.finish_recovery(True, 'late completion', 2002),
                       automation.cancel_recovery('late cancellation')):
            self.assertFalse(result['safety_state_valid'])
            self.assertFalse(result['automation_armed'])
            self.assertIn('safety state', result['recovery_safety_message'])
            self.assertIsNone(result['recovery_attempts_today'])
        current = self.state_file.read_bytes() if self.state_file.exists() else None
        self.assertEqual(current, original, 'invalid evidence must not be overwritten')

    def test_missing_corrupt_and_oversized_state_inhibits_recovery(self):
        self.state_file.unlink()
        self.assert_inhibited()
        for raw in (b'{broken', b'[]', b'null', b'{}', b'\xff', b'x' * (automation.MAX_STATE_BYTES + 1)):
            with self.subTest(raw=raw[:16]):
                self.state_file.write_bytes(raw)
                self.assert_inhibited()

    def test_missing_or_type_invalid_safety_fields_inhibit(self):
        valid = automation.default_state()
        bad = {'version': [True, 2], 'mode': [[], 'bogus'],
               'maintenance_mode': ['false', 0, None],
               'recent_recovery_attempts': [None, {}, [True], ['1000'], [-1]],
               'consecutive_failures': [True, -1, 1.5, '2'],
               'cooldown_until': [None, False, -1, 1.5, '0', 10 ** 100],
               'backoff_until': [False, -1, [], 10 ** 100],
               'healthy_since': [42, 'not a date']}
        for key, values in bad.items():
            missing = dict(valid); missing.pop(key)
            for candidate in [missing, *(dict(valid, **{key: value}) for value in values)]:
                with self.subTest(key=key, candidate=candidate):
                    self.state_file.write_text(json.dumps(candidate))
                    self.assert_inhibited()

    def test_valid_state_preserves_safety_fields_and_unknown_stays_unknown(self):
        valid = dict(automation.default_state(), maintenance_mode=True,
                     recent_recovery_attempts=[990, 1001], consecutive_failures=2,
                     cooldown_until=1100, backoff_until=1200)
        self.state_file.write_text(json.dumps(valid))
        loaded = automation.load_state()
        self.assertTrue(loaded['safety_state_valid'])
        for key in valid: self.assertEqual(loaded[key], valid[key])
        health = {'asterisk': 'unknown', 'asterisk_evidence': {'service': {'status': 'unknown'}}}
        automation.observe_health(health, 1000)
        self.assertEqual(health['asterisk'], 'unknown')
        self.assertFalse(automation.recovery_allowed(health, 1000))
        self.assertEqual(automation.load_state()['recent_recovery_attempts'], [990, 1001])

    def test_maintenance_exit_does_not_enable_disabled_recovery(self):
        with patch.object(automation, 'RECOVERY_ENABLED', False):
            automation.set_maintenance(True, now=1000)
            state = automation.set_maintenance(False, now=1001)
            self.assertFalse(state['recovery_enabled'])
            self.assertFalse(state['automation_armed'])
            self.assertNotIn('actions resumed', state['last_result'])

    def test_isolated_recovery_verifies_and_resumes(self):
        self.assertTrue(automation.recovery_allowed(stopped(1000), 1000))
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
        self.assertFalse(automation.recovery_allowed(stopped(1030), 1030))

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
        self.assertFalse(automation.recovery_allowed(stopped(1001), 1001))
        resumed = automation.set_maintenance(False, 1002)
        self.assertTrue(resumed["automation_armed"])
        self.assertTrue(automation.recovery_allowed(stopped(1002), 1002))

    def test_persistence_and_malformed_state(self):
        automation.set_maintenance(True, 1000)
        self.assertTrue(automation.load_state()["maintenance_mode"])
        self.state_file.write_text("{broken", encoding="utf-8")
        state = automation.load_state()
        self.assertFalse(state['safety_state_valid'])
        self.assertTrue(state['maintenance_mode'])
        automation.save_state(state)
        self.assertEqual(self.state_file.read_text(), '{broken')

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
