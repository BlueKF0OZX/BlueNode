import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import connectivity


NOW = datetime(2026, 9, 4, 12, 0, tzinfo=timezone.utc)


class ConnectivityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.state_patch = patch.object(connectivity, "STATE_FILE", Path(self.temp.name) / "connectivity.json")
        self.emit_patch = patch.object(connectivity, "emit")
        self.state_patch.start()
        self.emit = self.emit_patch.start()

    def tearDown(self):
        self.emit_patch.stop()
        self.state_patch.stop()
        self.temp.cleanup()

    @staticmethod
    def healthy():
        return {"interface": True, "gateway": True, "dns": True,
                "internet": True, "allstar": True}

    def sustained(self, field):
        checks = self.healthy()
        checks[field] = False
        first = connectivity.update(checks, NOW)
        second = connectivity.update(checks, NOW + timedelta(seconds=30))
        self.assertEqual(first["diagnosis"], "transient")
        self.assertFalse(first["sustained"])
        self.assertEqual(connectivity.legacy_internet_state(first), "online")
        self.assertTrue(second["sustained"])
        return second

    def test_everything_healthy(self):
        self.assertGreaterEqual(connectivity.INTERVAL_SECONDS, 10)
        state = connectivity.update(self.healthy(), NOW)
        self.assertEqual(state["status"], "healthy")
        self.assertEqual(state["diagnosis"], "healthy")
        self.assertEqual(connectivity.legacy_internet_state(state), "online")

    def test_gateway_unavailable(self):
        state = self.sustained("gateway")
        self.assertEqual((state["diagnosis"], state["status"]), ("gateway_failure", "offline"))

    def test_local_interface_unavailable(self):
        state = self.sustained("interface")
        self.assertEqual((state["diagnosis"], state["status"]),
                         ("local_network_failure", "offline"))

    def test_dns_failure_with_gateway_healthy(self):
        state = self.sustained("dns")
        self.assertEqual((state["diagnosis"], state["status"]), ("dns_failure", "degraded"))
        self.assertTrue(state["checks"]["gateway"])
        self.assertEqual(connectivity.legacy_internet_state(state), "online")

    def test_external_internet_failure_with_lan_healthy(self):
        state = self.sustained("internet")
        self.assertEqual(state["diagnosis"], "external_internet_failure")
        self.assertEqual(state["status"], "offline")
        self.assertTrue(state["checks"]["interface"])

    def test_allstar_failure_with_general_internet_healthy(self):
        state = self.sustained("allstar")
        self.assertEqual((state["diagnosis"], state["status"]), ("allstar_failure", "degraded"))
        self.assertTrue(state["checks"]["internet"])

    def test_verified_recovery_requires_confirmation(self):
        self.sustained("gateway")
        first = connectivity.update(self.healthy(), NOW + timedelta(seconds=60))
        second = connectivity.update(self.healthy(), NOW + timedelta(seconds=90))
        self.assertEqual(first["diagnosis"], "recovering")
        self.assertEqual(connectivity.legacy_internet_state(first), "offline")
        self.assertEqual(second["diagnosis"], "healthy")
        self.assertFalse(second["sustained"])

    def test_stale_state_clears(self):
        connectivity.update(self.healthy(), NOW)
        state = connectivity.public_state(NOW + timedelta(seconds=connectivity.STALE_SECONDS + 1))
        self.assertEqual(state["diagnosis"], "unavailable")
        self.assertTrue(state["stale"])

    def test_malformed_state_fails_safely(self):
        connectivity.STATE_FILE.write_text("bad json")
        self.assertEqual(connectivity.public_state(NOW)["status"], "unavailable")
        connectivity.STATE_FILE.write_text('{"consecutive_failures": []}')
        self.assertEqual(connectivity.update(self.healthy(), NOW)["status"], "healthy")

    def test_events_are_emitted_only_for_transitions(self):
        connectivity.update(self.healthy(), NOW)
        checks = self.healthy()
        checks["dns"] = False
        connectivity.update(checks, NOW + timedelta(seconds=30))
        connectivity.update(checks, NOW + timedelta(seconds=60))
        connectivity.update(checks, NOW + timedelta(seconds=90))

        events = [call.args[0] for call in self.emit.call_args_list]
        self.assertEqual(events, ["CONNECTIVITY.TRANSIENT", "CONNECTIVITY.DNS_FAILURE"])


if __name__ == "__main__":
    unittest.main()
